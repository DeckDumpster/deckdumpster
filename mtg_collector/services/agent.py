"""Tool-using Claude agent service for MTG card identification from photos."""

import json
import sqlite3
import sys
import time

import anthropic
import httpx

from mtg_collector.db.connection import get_db_path
from mtg_collector.services.claude import ClaudeVision

AGENT_MODEL_HAIKU = "claude-haiku-4-5-20251001"
AGENT_MODEL_SONNET = "claude-sonnet-4-6"
VISION_MODEL = "claude-opus-4-6"
DEFAULT_MAX_CALLS = 12
LARGE_FRAGMENT_THRESHOLD = 70
CONTEXT_UPGRADE_THRESHOLD = 8_000  # input tokens; switch Haiku → Sonnet if context grows large

CARD_STRUCTURE = """\
CARD LAYOUT (top to bottom):
  - Title (top left of card)
  - Colorless portion of a mana cost (optional; top right of card)
  - Type and Subtype (middle left of card, below the art; subtype optional)
  - Rules text (below type line — may be blank on vanilla creatures)
  - Flavor text (italic, below rules, not always present)
  - Bottom-left info area (format varies by era — see BOTTOM-LEFT INFO below)
  - Bottom-right corner: power/toughness (creatures only)

Some cards have wildly different faces, like titles at the bottom or rules text directly below the title.
Usually if text appears directly below the title of a card, it is rules text. Use your judgment
and knowledge as an expert.

Rules text is about effect to the game state. It will mention things that the card does to other entities.
Some cards have no rules text, some cards have no flavor text, but all cards have one or both.
You can search by flavor text or rules text, which can be a powerful aid.

There may be large vertical gaps between the title and the type line — that is the card art.
Cards with no rules text will have another gap between the type line and the collector info.
All of these text regions belong to the SAME card.

BOTTOM-LEFT INFO — this area has changed across Magic's history. All info below is on
separate lines from each other; items are NOT adjacent on the same line.

Era 1: Alpha through Alliances (1993–1996)
  - "Illus. <Artist Name>" (centered below text box)
  - Copyright line (year added from Legends onward)
  - NO collector number, NO set code

Era 2: Exodus through 7th Edition (1998–2002) — pre-modern frame
  - "Illus. <Artist Name>" (centered)
  - "CN/TOTAL" collector number (e.g. "47/143") + copyright/trademark on same line
  - NO set code printed

Era 3: 8th Edition through Magic 2014 (2003–2013) — modern frame
  - "Illus. <Artist Name>" (left-aligned)
  - "CN/TOTAL" collector number + copyright/trademark
  - NO set code printed

Era 4: Magic 2015 through Phyrexia: All Will Be One (2014–2023) — M15 frame
  - Black info bar at bottom of card (the "OCR area")
  - Line 1: "CN/TOTAL RARITY" (e.g. "122/269 R") — rarity is C/U/R/M
  - Line 2: "SET . LANG" (e.g. "M15 . EN") — 3-letter set code, 2-letter language
  - Line 3: paintbrush icon + Artist Name (replaces "Illus.")
  - Copyright/trademark on right side of black bar

Era 5: March of the Machine onward (2023–present)
  - Same black info bar as Era 4
  - Line 1: "RARITY+4DIGIT_CN" (e.g. "R0092", "C0145") — rarity prefix, 4-digit padded CN
  - Line 2: "SET . LANG" (same as Era 4)
  - Line 3: paintbrush icon + Artist Name
  - The fraction format "CN/TOTAL" was abandoned

Across all eras, some collector numbers have letter suffixes (a, b, s, z) or prefixes (A-).
The paintbrush icon before the artist name may be misread as digits (e.g. "00661") — if you
see unexpected digits directly before an artist name, they are likely the paintbrush icon,
not a real number."""

SYSTEM_PROMPT = """\
You are an expert Magic: The Gathering card identifier running in an automated pipeline.
You receive OCR text fragments from a photo of a single MTG card. The text
fragments indicate position via bounding boxes,
text in those boxes, and confidence scores from OCR.

You are NOT interactive. Do not address the user, ask questions, or make suggestions like
"if you can see..." or "you could check...". Do not use markdown formatting, bold text, or
headers. Just reason concisely and call tools.

YOUR JOB:
Identify the card and return ALL plausible printing candidates as DATABASE PRINTING IDs
so a human can pick the right one.
OCR may have detected partial text fragments from other cards or sources
in the background that you should ignore.

Strategy:
1. Interpret OCR fragments to find card data. The most important indicators are name, set code, and collector number.
2. Search to verify using query_local_db — when disambiguating printings, JOIN sets to get
   set_name and released_at so you can reason about which sets are plausible.
   ALWAYS SELECT printing_id in your queries — you will need these IDs for your final output.
3. If OCR and DB queries leave multiple plausible printings, consider calling analyze_image.
   Always search the DB first so you have context to interpret the vision results.
   Do NOT use analyze_image to distinguish older set reprints that differ only by border color,
   set symbol, or frame era (e.g. 3ed vs 4ed vs 5ed, Alpha vs Beta) — just return all of those.
   It IS useful when candidates differ in ways OCR cannot capture, like full-art vs normal frame,
   alternate art, or promo vs regular versions of newer cards.
4. If you have found zero candidates, call analyze_image before giving up. Never return
   an empty result without trying vision first.
5. Stop calling tools and emit ALL remaining candidate printing_ids.

OCR BOUNDING BOXES

Cards will ALWAYS be positioned vertically in an image. The aspect ratio of a Magic card is 63:88 (wide:tall).

""" + CARD_STRUCTURE + """

USING OCR DATA TO SEARCH
The most reliable indicators of a card are its name, set code, and collector number.
For older cards without a set code or collector number, artist and flavor text are
the best tools to narrow potential printings. If a date is present
Card text can be used also, but older card rules text wording may not match the card database.

DISAMBIGUATION RULE — this is critical:
If you cannot distinguish between printings of a card, you MUST return ALL plausible
printing_ids. This is not a failure — returning multiple candidates IS the correct output.
A human will pick the right one.
In particular, you can NEVER tell "foil" from "nonfoil" from OCR text alone. In these
cases, return both options.

Example: OCR shows card name "Grizzly Bears" with artist "Jeff A. Menges" and no date.
DB query returns many printings, all with identical features: Unlimited (2ed), Revised (3ed)
both do not have dates, and on several sets, dates are extremely small: OCR may have just missed it.
CORRECT: return ALL printing_ids from the query.
WRONG: return a single printing_id and hope it's right.

This rule applies even after calling analyze_image — if vision analysis cannot definitively
resolve the printing, still return all remaining plausible printing_ids.

KNOWN HARD CASES
The DISAMBIGUATION RULE applies in these cases: Return all reasonable candidates.
* 3rd Edition (Revised, set code 3ed), 4th Edition (4ed), and 5th edition (5ed) are
  very similar: White-bordered, no set symbol, similar wording. 4th edition and 5th edition
  have dates under the artist line, so high-confidence OCR can help distinguish, but 4ed and 5ed
  are nearly identical.
* Similarly, distinguishing between Alpha and Beta can be difficult even for humans: Both
  black-bordered with identical wordings across most cards.
* OCR gives you text printed on the card. The card database contains modern wordings of rules
  text on cards (aka Oracle text). These can be very different, so have caution when doing
  rules text matching.
* Sometimes photos contain cards that are clearly visible in the foreground, and others that are
  in the background, partly visible. Only identify foreground cards.
"""

SYSTEM_CONTENT = [
    {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
]

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "printing_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "fragment_indices": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                    "notes": {"type": "string"},
                },
                "required": ["name", "printing_ids", "fragment_indices"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["cards"],
    "additionalProperties": False,
}

_QUERY_TOOL_NOTES = (
    "When listing candidate printings for disambiguation, JOIN sets to include "
    "set_name and released_at — this helps reason about which sets are plausible. "
    "Always use LEFT JOIN since not all sets are guaranteed to have a row.\n\n"
    "CRITICAL: Always SELECT p.printing_id in your queries. Your final output must "
    "contain printing_id values from the database. These are UUID strings.\n\n"
    "Common mistakes to avoid:\n"
    "- There is NO 'name' column on printings — name is on cards. JOIN cards to get it.\n"
    "- There is NO 'foil' column — use finishes (JSON TEXT, e.g. '[\"nonfoil\"]')\n"
    "- There is NO 'set_name' column on printings — set_name is on sets. JOIN sets to get it.\n"
    "- Always qualify set_code with a table alias (e.g. p.set_code) to avoid ambiguity.\n"
    "- Use LIKE with % for substring matching; COLLATE NOCASE for case-insensitivity\n"
    "- Do NOT use LIMIT when fetching printings of a specific card — you need all rows to find the right printing\n"
    "- Use LIMIT only for broad/exploratory queries (e.g. browsing sets)\n"
    "- Only SELECT is permitted"
)

_ANALYZE_IMAGE_TOOL = {
    "name": "analyze_image",
    "description": (
        "Use Claude Vision to directly analyze the full card image. "
        "Can only be called ONCE per session. Expensive — always search the DB first.\n\n"
        "Do NOT use this to distinguish older set reprints that differ only by border color "
        "or frame era (e.g. 3ed vs 4ed, Alpha vs Beta) — just return all candidates.\n\n"
        "DO use when candidates differ in ways OCR cannot capture: full-art vs normal frame, "
        "alternate art, promo vs regular for newer cards, or when OCR text is too garbled "
        "to identify the card name at all."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
    "cache_control": {"type": "ephemeral"},
}

_AGENT_TABLES = ("cards", "printings", "sets")


def _build_tools(conn: sqlite3.Connection) -> list[dict]:
    """Build tool definitions with schema DDL read from the live database."""
    ddl_parts = []
    for table in _AGENT_TABLES:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if row:
            ddl_parts.append(row[0] + ";")
    schema_ddl = "\n\n".join(ddl_parts)

    description = (
        "Run a read-only SELECT query against the local card database.\n\n"
        f"Schema (these are the ONLY tables and columns that exist):\n\n{schema_ddl}\n\n"
        + _QUERY_TOOL_NOTES
    )
    query_tool = {
        "name": "query_local_db",
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "A SELECT statement to run against the local DB",
                }
            },
            "required": ["sql"],
        },
    }
    return [query_tool, _ANALYZE_IMAGE_TOOL]


def _trace(msg: str, status_callback, trace_lines: list[str] | None = None) -> None:
    if trace_lines is not None:
        trace_lines.append(msg)
    if status_callback:
        status_callback(msg)
    else:
        print(msg, file=sys.stderr)


def _format_fragments(fragments: list[dict]) -> str:
    lines = []
    for i, f in enumerate(fragments):
        b = f["bbox"]
        lines.append(
            f'[{i}] (x={int(b["x"])},y={int(b["y"])} w={int(b["w"])},h={int(b["h"])}'
            f' conf={f["confidence"]:.2f}): "{f["text"]}"'
        )
    return "\n".join(lines)


_DB_ROW_CAP = 200
_DB_CHAR_CAP = 12_000


def _tool_query_local_db(sql: str, conn: sqlite3.Connection) -> str:
    sql_stripped = sql.strip()
    if not sql_stripped.upper().startswith("SELECT"):
        return "Error: only SELECT statements are permitted"
    try:
        rows = conn.execute(sql_stripped).fetchall()
    except sqlite3.OperationalError as e:
        return f"SQL error: {e}"
    if not rows:
        return "No results found in local cache"
    cols = rows[0].keys()
    lines = []
    total_chars = 0
    for i, row in enumerate(rows):
        if i >= _DB_ROW_CAP:
            lines.append(
                f"[Truncated: row cap of {_DB_ROW_CAP} reached. "
                f"{len(rows) - _DB_ROW_CAP} rows omitted. Refine your query.]"
            )
            break
        line = " | ".join(str(row[c]) for c in cols)
        total_chars += len(line) + 1
        if total_chars > _DB_CHAR_CAP:
            lines.append(
                f"[Truncated: character cap of {_DB_CHAR_CAP} reached. "
                f"{len(rows) - i} rows omitted. Refine your query.]"
            )
            break
        lines.append(line)
    return "\n".join(lines)


def _tool_analyze_image(image_path: str, client: anthropic.Anthropic) -> tuple[str, object]:
    """Returns (description_text, response.usage)."""
    vision = ClaudeVision(model=VISION_MODEL)
    image_data = vision.encode_image(image_path)
    media_type = vision._get_media_type(image_path)

    response = client.messages.create(
        model=VISION_MODEL,
        max_tokens=4000,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "This is a photo of a single Magic: The Gathering card. "
                            "Only describe what you can clearly see; if something is "
                            "unclear or not visible, write \"not visible\" for that field. "
                            "If text is very small, you should assume it is not visible. "
                            "If you recognize a set icon, that is valuable if you are certain.\n\n"
                            "Respond in this exact format:\n\n"
                            "CARD NAME:\nMANA COST:\nTYPE LINE:\n"
                            "RULES TEXT (first line or key phrases):\n"
                            "FLAVOR TEXT (if visible):\n"
                            "POWER/TOUGHNESS or LOYALTY:\n\n"
                            "FRAME AND STRUCTURE:\n"
                            "  Face structure: [normal / full-art / borderless / extended art / "
                            "split / flip / saga / class / adventure / leveler / battle / planeswalker]\n"
                            "  Frame era: [pre-8th / modern (8th-M14) / M15+ / other]\n\n"
                            "SET IDENTIFICATION:\n"
                            "  Set symbol description:\n"
                            "  Set symbol rarity color: [black(common) / silver(uncommon) / "
                            "gold(rare) / orange-red(mythic) / not visible]\n"
                            "  Collector number:\n"
                            "  Set code:\n\n"
                            "ARTIST:\n\n"
                            "ART DESCRIPTION (2-3 sentences, focus on what makes this art unique):\n\n"
                            + CARD_STRUCTURE
                        ),
                    },
                ],
            }
        ],
    )
    text = ""
    for block in response.content:
        if block.type == "text":
            text += block.text
    return text, response.usage


def _has_tool_use(response) -> bool:
    return any(block.type == "tool_use" for block in response.content)


def _call_api(fn, status_callback, trace_lines=None, **kwargs):
    """Call fn(**kwargs) with retries on 529 Overloaded and 429 Rate Limit errors.

    On 429: switches Haiku->Sonnet immediately (per-model rate limit), waits on Sonnet.
    On 529: after 3 Haiku failures switches to Sonnet for remaining retries.
    """
    haiku_529_count = 0
    for attempt in range(6):
        try:
            return fn(**kwargs)
        except anthropic.APIStatusError as e:
            is_last = attempt == 5
            if e.status_code == 429:
                if is_last:
                    raise
                if kwargs.get("model") == AGENT_MODEL_HAIKU:
                    kwargs["model"] = AGENT_MODEL_SONNET
                    _trace("[AGENT] Haiku rate limited (429), switching to Sonnet", status_callback, trace_lines)
                    continue
                retry_after = e.response.headers.get("retry-after")
                wait = float(retry_after) if retry_after else 30
                _trace(f"[AGENT] Rate limited (429), retrying in {wait:.0f}s...", status_callback, trace_lines)
                time.sleep(wait)
            elif e.status_code == 529:
                if is_last:
                    raise
                haiku_529_count += 1
                if haiku_529_count >= 3 and kwargs.get("model") == AGENT_MODEL_HAIKU:
                    kwargs["model"] = AGENT_MODEL_SONNET
                    _trace("[AGENT] Switching to Sonnet after 3 Haiku overload errors", status_callback, trace_lines)
                wait = 3 * (2 ** attempt)
                _trace(f"[AGENT] Overloaded (529), retrying in {wait}s...", status_callback, trace_lines)
                time.sleep(wait)
            else:
                raise


def run_agent(
    image_path: str,
    ocr_fragments: list[dict],
    max_calls: int | None = None,
    status_callback=None,
    trace_out: list[str] | None = None,
) -> tuple[list[dict], list[str], dict]:
    """Run the tool-using agent to identify MTG cards from an image.

    Args:
        image_path: Path to the card image file.
        ocr_fragments: Pre-computed OCR fragments from run_ocr_with_boxes().
        max_calls: Maximum tool calls. Defaults to max(DEFAULT_MAX_CALLS,
                   int(DEFAULT_MAX_CALLS * len(ocr_fragments) / 10)).
        status_callback: Optional callable for trace messages (replaces stderr).
        trace_out: Optional list to accumulate trace lines in-place. If provided,
                   the caller retains access to partial trace even if an exception
                   is raised.

    Returns:
        (cards, trace, usage) where cards is a list of card dicts, trace is the
        list of all trace lines emitted during the run, and usage is a dict of
        {model: {input, output}} token counts for haiku/sonnet/opus.
    """
    n = len(ocr_fragments)
    if max_calls is None:
        max_calls = max(DEFAULT_MAX_CALLS, int(DEFAULT_MAX_CALLS * n / 10))
    agent_model = AGENT_MODEL_SONNET if n > LARGE_FRAGMENT_THRESHOLD else AGENT_MODEL_HAIKU

    client = anthropic.Anthropic(
        timeout=httpx.Timeout(600.0, connect=10.0),
    )
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    tools = _build_tools(conn)

    trace_lines: list[str] = trace_out if trace_out is not None else []
    usage: dict[str, dict[str, int]] = {
        "haiku": {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0},
        "sonnet": {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0},
        "opus": {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0},
    }

    _trace(f"[AGENT] Starting with {n} OCR fragments (max_calls={max_calls}, model={agent_model})", status_callback, trace_lines)

    initial_content = (
        f"I have run OCR on the image `{image_path}`. "
        f"Here are the {len(ocr_fragments)} text fragments found:\n\n"
        + _format_fragments(ocr_fragments)
        + "\n\nPlease identify the MTG card in this image."
    )
    messages = [{"role": "user", "content": initial_content}]

    tool_call_count = 0
    vision_used = [False]
    vision_cached_result = [None]
    nudge_sent = False
    response = None

    while tool_call_count < max_calls:
        response = _call_api(
            client.messages.create,
            status_callback,
            trace_lines=trace_lines,
            model=agent_model,
            max_tokens=4000,
            temperature=0,
            system=SYSTEM_CONTENT,
            tools=tools,
            messages=messages,
        )

        model_key = "sonnet" if "sonnet" in response.model else "haiku"
        usage[model_key]["input"] += response.usage.input_tokens
        usage[model_key]["output"] += response.usage.output_tokens
        usage[model_key]["cache_read"] += getattr(response.usage, "cache_read_input_tokens", 0) or 0
        usage[model_key]["cache_creation"] += getattr(response.usage, "cache_creation_input_tokens", 0) or 0

        # Persist model upgrade if _call_api switched due to rate limit/overload
        if agent_model == AGENT_MODEL_HAIKU and model_key == "sonnet":
            agent_model = AGENT_MODEL_SONNET
            _trace("[AGENT] Persisting upgrade to Sonnet", status_callback, trace_lines)

        model_label = model_key
        for block in response.content:
            if block.type == "text":
                _trace(f"[AGENT/{model_label}] {block.text.strip()}", status_callback, trace_lines)
            elif block.type == "tool_use":
                _trace(f"[TOOL CALL/{model_label}] {block.name}: {json.dumps(block.input)}", status_callback, trace_lines)

        if (
            agent_model == AGENT_MODEL_HAIKU
            and response.usage.input_tokens >= CONTEXT_UPGRADE_THRESHOLD
        ):
            agent_model = AGENT_MODEL_SONNET
            _trace(
                f"[AGENT] Context at {response.usage.input_tokens} tokens, upgrading to Sonnet",
                status_callback,
                trace_lines,
            )

        if response.stop_reason == "end_turn" or not _has_tool_use(response):
            break

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            tool_call_count += 1
            name = block.name
            inputs = block.input

            if name == "query_local_db":
                result = _tool_query_local_db(inputs.get("sql", ""), conn)
            elif name == "analyze_image":
                if vision_used[0]:
                    result = vision_cached_result[0] or (
                        "[analyze_image already called — use query_local_db instead.]"
                    )
                else:
                    result, vision_usage = _tool_analyze_image(image_path, client)
                    usage["opus"]["input"] += vision_usage.input_tokens
                    usage["opus"]["output"] += vision_usage.output_tokens
                    vision_used[0] = True
                    vision_cached_result[0] = result
            else:
                result = f"Unknown tool: {name}"

            if name == "analyze_image":
                trace_result = result
            else:
                trace_result = f"{result[:500]}{'...' if len(result) > 500 else ''}"
            _trace(
                f"[TOOL RESULT] {name}: {trace_result}",
                status_callback,
                trace_lines,
            )
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                }
            )

        messages.append({"role": "assistant", "content": response.content})

        # Nudge the agent if it's struggling
        if tool_call_count >= 6 and not vision_used[0] and not nudge_sent:
            nudge = (
                f"You've used {tool_call_count} tool calls. If you're having trouble, "
                f"try Claude Vision, followed by more SQL queries using the data it returns."
            )
            tool_results.append({"type": "text", "text": nudge})
            nudge_sent = True
            _trace(f"[AGENT] Injected nudge at {tool_call_count} tool calls", status_callback, trace_lines)

        messages.append({"role": "user", "content": tool_results})

    _trace(f"[FINAL] Tool calls used: {tool_call_count}/{max_calls}", status_callback, trace_lines)

    FINAL_PROMPT = (
        "Output ALL IDENTIFIED CANDIDATES for the card now. "
        "Each card entry must include a printing_ids array with ALL plausible "
        "printing_id values from the database, most likely first. "
        "Include the card name for reference. "
    )
    # If the last response was end_turn it hasn't been appended to messages yet.
    # Add it so the conversation is complete, then ask for the final answer.
    if response is not None and response.stop_reason == "end_turn":
        messages.append({"role": "assistant", "content": response.content})
    # Both paths get the same final prompt.
    messages.append({"role": "user", "content": FINAL_PROMPT})

    _trace("[FINAL] Requesting structured output...", status_callback, trace_lines)
    final_response = _call_api(
        client.messages.create,
        status_callback,
        trace_lines=trace_lines,
        model=agent_model,
        max_tokens=2000,
        temperature=0,
        system=SYSTEM_CONTENT,
        messages=messages,
        output_config={
            "format": {
                "type": "json_schema",
                "schema": OUTPUT_SCHEMA,
            }
        },
    )
    final_model_key = "sonnet" if "sonnet" in final_response.model else "haiku"
    usage[final_model_key]["input"] += final_response.usage.input_tokens
    usage[final_model_key]["output"] += final_response.usage.output_tokens
    usage[final_model_key]["cache_read"] += getattr(final_response.usage, "cache_read_input_tokens", 0) or 0
    usage[final_model_key]["cache_creation"] += getattr(final_response.usage, "cache_creation_input_tokens", 0) or 0

    cache_read_total = sum(u["cache_read"] for u in usage.values())
    cache_creation_total = sum(u["cache_creation"] for u in usage.values())
    _trace(
        f"[USAGE] haiku={usage['haiku']['input']}in/{usage['haiku']['output']}out "
        f"sonnet={usage['sonnet']['input']}in/{usage['sonnet']['output']}out "
        f"opus={usage['opus']['input']}in/{usage['opus']['output']}out "
        f"cache_read={cache_read_total} cache_creation={cache_creation_total}",
        status_callback,
        trace_lines,
    )

    result = json.loads(final_response.content[0].text)
    _trace(f"[FINAL OUTPUT]\n{json.dumps(result, indent=2)}", status_callback, trace_lines)
    return result["cards"], trace_lines, usage
