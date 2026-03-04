"""Commander deck-building agent using Claude + Scryfall otag classification."""

import json
import sqlite3
import sys
import time

import anthropic
import httpx
import requests

AGENT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_CALLS = 30
SCRYFALL_SEARCH_URL = "https://api.scryfall.com/cards/search"

DECK_TEMPLATE = """\
## Commander Deck Template (Command Zone Ep 658)

Target: 99 cards (excluding commander) in these categories:

| Category         | Target | Notes                                              |
|------------------|--------|----------------------------------------------------|
| Lands            | 38     | Includes utility lands                             |
| Ramp             | 10     | Prioritize 2-mana rocks/spells                     |
| Card Advantage   | 12     | Draw, impulse, self-mill, selection                |
| Targeted Removal | 12     | Destroy, exile, bounce, counterspells, pacify      |
| Board Wipes      | 6      | Mass removal / reset buttons                       |
| Standalone       | ~25    | Threats, win conditions, strategy execution        |
| Enhancers        | ~10    | Synergy multipliers — amplify standalones/commander |
| Enablers         | ~7     | Utility glue, gap-fillers, cover weaknesses        |

These categories overlap. The totals sum to ~120 slots for 99 cards because cards
serve multiple roles. A Swords to Plowshares is "targeted removal" AND potentially
an "enabler". Count multi-role cards toward EACH category they fulfill.

## Mana Curve Targets (nonland cards)

| Mana Value | Card Count |
|------------|------------|
| 0-1        | 5-10       |
| 2          | 14-20      |
| 3          | 10-18      |
| 4          | 6-12       |
| 5          | 5-10       |
| 6          | 3-6        |
| 7+         | 1-5        |

Average CMC target: 2.8-3.5 for typical decks.

## Commander-Dependent Adjustments

- Commander provides card draw → fewer card advantage slots
- Commander IS removal → fewer removal slots
- Commander is cheap (1-3 MV) → can shave a land or two
- Commander is expensive (6+ MV) → more ramp, possibly 39 lands
"""

_QUERY_TOOL_NOTES = (
    "Common column clarifications:\n"
    "- Card name is on `cards` table. JOIN cards to get it.\n"
    "- There is NO 'foil' column — use finishes (JSON TEXT, e.g. '[\"nonfoil\"]')\n"
    "- set_name is on `sets` table. JOIN sets to get it.\n"
    "- Always qualify set_code with a table alias to avoid ambiguity.\n"
    "- Use COLLATE NOCASE for case-insensitive name matching.\n"
    "- Only SELECT is permitted."
)

_SCRYFALL_TOOL_NOTES = (
    "Searches the full Scryfall database (ALL cards, not just owned).\n"
    "Results include name, type_line, mana_cost, and cmc.\n"
    "Cross-reference results with query_local_db to check if you own them.\n\n"
    "Syntax examples:\n"
    '  otag:ramp f:commander id<=WUB\n'
    '  t:creature kw:hexproof mv<=3 id<=RG\n'
    '  o:"destroy target" t:instant id<=B\n'
    '  (otag:mana-rock or otag:mana-dork) mv<=2 f:commander id<=WU\n\n'
    "Results are ordered by EDHREC rank (most popular first), capped at 100.\n"
    "Rate limited — use targeted queries, not broad sweeps."
)

_AGENT_TABLES = ("cards", "printings", "sets", "collection", "decks")

_DB_ROW_CAP = 200
_DB_CHAR_CAP = 12_000


# ── Scryfall search ──────────────────────────────────────────────────

class _ScryfallSearchClient:
    """Lightweight Scryfall search API client with rate limiting."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "MTGCollectionTool/2.0"})
        self.last_request = 0.0

    def _rate_limit(self):
        elapsed = time.time() - self.last_request
        if elapsed < 0.1:
            time.sleep(0.1 - elapsed)
        self.last_request = time.time()

    def search(self, query: str, max_results: int = 100) -> list[dict]:
        """Search Scryfall, return list of card dicts (name, type_line, mana_cost, cmc)."""
        results = []
        url = SCRYFALL_SEARCH_URL
        params = {"q": query, "order": "edhrec"}

        while len(results) < max_results:
            self._rate_limit()
            resp = self.session.get(url, params=params)
            if resp.status_code == 404:
                return []  # no results
            if resp.status_code == 429:
                time.sleep(1.0)
                continue
            resp.raise_for_status()
            data = resp.json()
            for card in data.get("data", []):
                results.append({
                    "name": card.get("name", ""),
                    "type_line": card.get("type_line", ""),
                    "mana_cost": card.get("mana_cost", ""),
                    "cmc": card.get("cmc", 0),
                })
                if len(results) >= max_results:
                    break
            if not data.get("has_more"):
                break
            url = data["next_page"]
            params = None  # next_page is a full URL

        return results


# ── Pre-classification ───────────────────────────────────────────────

def _color_identity_clause(ci: list[str]) -> str:
    """SQL WHERE clause ensuring card's color_identity is subset of ci."""
    if not ci:
        return "NOT EXISTS (SELECT 1 FROM json_each(c2.color_identity))"
    colors_list = ", ".join(f"'{c}'" for c in ci)
    return (
        f"NOT EXISTS ("
        f"SELECT 1 FROM json_each(c2.color_identity) "
        f"WHERE json_each.value NOT IN ({colors_list})"
        f")"
    )


def _ci_string(ci: list[str]) -> str:
    """Convert color identity list to Scryfall id<= string, e.g. ['W','U','B'] -> 'WUB'."""
    order = "WUBRG"
    return "".join(c for c in order if c in ci) or "C"


def _scryfall_classify_batch(
    card_names: list[str], otag: str, ci: str, scryfall: _ScryfallSearchClient
) -> set[str]:
    """Query Scryfall for which of the given card names match an otag. Returns matching names."""
    matching = set()
    # Batch names into groups to stay under URL length limits
    batch_size = 25
    for i in range(0, len(card_names), batch_size):
        batch = card_names[i:i + batch_size]
        name_clauses = " or ".join(f'!"{n}"' for n in batch)
        query = f"({name_clauses}) otag:{otag} f:commander id<={ci}"
        try:
            results = scryfall.search(query, max_results=175)
            for card in results:
                matching.add(card["name"])
        except requests.exceptions.HTTPError:
            pass  # tag may not match any — that's fine
    return matching


def classify_owned_cards(
    conn: sqlite3.Connection, ci: list[str], commander_oracle_id: str,
    status_callback=None,
) -> dict[str, list[dict]]:
    """Pre-classify owned, unassigned, Commander-legal cards by functional category.

    Returns dict with keys: lands, ramp, card_advantage, targeted_removal,
    board_wipes, unclassified. Each value is a list of card dicts sorted by EDHREC rank.
    Cards can appear in multiple categories.
    """
    ci_clause = _color_identity_clause(ci)
    ci_str = _ci_string(ci)

    # Fetch all owned, unassigned cards in color identity
    # Pick one collection_id per oracle_id (best condition, prefer nonfoil)
    query = f"""
        SELECT c.id as collection_id, c.printing_id, c.finish, c.condition,
               c2.name, c2.oracle_id, c2.type_line, c2.mana_cost, c2.cmc,
               c2.oracle_text, c2.color_identity,
               json_extract(p.raw_json, '$.edhrec_rank') as edhrec_rank,
               p.set_code, p.collector_number
        FROM collection c
        JOIN printings p ON c.printing_id = p.printing_id
        JOIN cards c2 ON p.oracle_id = c2.oracle_id
        WHERE c.status = 'owned'
          AND c.deck_id IS NULL
          AND c.binder_id IS NULL
          AND c2.oracle_id != ?
          AND {ci_clause}
        ORDER BY
            c2.oracle_id,
            CASE c.condition
                WHEN 'Near Mint' THEN 1
                WHEN 'Lightly Played' THEN 2
                WHEN 'Moderately Played' THEN 3
                WHEN 'Heavily Played' THEN 4
                WHEN 'Damaged' THEN 5
            END,
            CASE c.finish WHEN 'nonfoil' THEN 1 ELSE 2 END
    """
    rows = conn.execute(query, (commander_oracle_id,)).fetchall()

    # Deduplicate: one collection entry per oracle_id (except basic lands)
    seen_oracle: dict[str, dict] = {}
    basic_land_names = {"Plains", "Island", "Swamp", "Mountain", "Forest",
                        "Wastes", "Snow-Covered Plains", "Snow-Covered Island",
                        "Snow-Covered Swamp", "Snow-Covered Mountain",
                        "Snow-Covered Forest"}
    all_cards: list[dict] = []

    for row in rows:
        card = dict(row)
        oid = card["oracle_id"]
        is_basic = card["name"] in basic_land_names
        if not is_basic and oid in seen_oracle:
            continue
        seen_oracle[oid] = card
        all_cards.append(card)

    if status_callback:
        status_callback(f"Found {len(all_cards)} eligible cards in collection")

    # Classify lands locally
    lands = []
    nonlands = []
    for card in all_cards:
        tl = card.get("type_line") or ""
        if "Land" in tl:
            lands.append(card)
        else:
            nonlands.append(card)

    # Sort by EDHREC rank (lower = more popular)
    def by_rank(c):
        r = c.get("edhrec_rank")
        return r if r is not None else 999999

    lands.sort(key=by_rank)

    # Batch-classify nonlands via Scryfall otags
    nonland_names = [c["name"] for c in nonlands]
    scryfall = _ScryfallSearchClient()

    categories = {
        "ramp": "ramp",
        "card_advantage": "card-advantage",
        "targeted_removal": "removal",
        "board_wipes": "board-wipe",
    }

    classified: dict[str, list[dict]] = {"lands": lands}
    classified_names: set[str] = set()

    for cat_key, otag in categories.items():
        if status_callback:
            status_callback(f"Classifying: {cat_key} (otag:{otag})")
        matching_names = _scryfall_classify_batch(nonland_names, otag, ci_str, scryfall)

        # For targeted_removal, exclude board wipes
        if cat_key == "targeted_removal":
            wipe_names = _scryfall_classify_batch(
                list(matching_names), "board-wipe", ci_str, scryfall
            )
            matching_names -= wipe_names

        cat_cards = [c for c in nonlands if c["name"] in matching_names]
        cat_cards.sort(key=by_rank)
        classified[cat_key] = cat_cards
        classified_names.update(matching_names)

    # Everything not classified goes to unclassified (potential standalones/enhancers/enablers)
    unclassified = [c for c in nonlands if c["name"] not in classified_names]
    unclassified.sort(key=by_rank)
    classified["unclassified"] = unclassified

    return classified


# ── Tool implementations ─────────────────────────────────────────────

def _tool_query_local_db(sql: str, conn: sqlite3.Connection) -> str:
    sql_stripped = sql.strip()
    if not sql_stripped.upper().startswith("SELECT"):
        return "Error: only SELECT statements are permitted"
    try:
        rows = conn.execute(sql_stripped).fetchall()
    except sqlite3.OperationalError as e:
        return f"SQL error: {e}"
    if not rows:
        return "No results found"
    cols = rows[0].keys()
    lines = []
    total_chars = 0
    for i, row in enumerate(rows):
        if i >= _DB_ROW_CAP:
            lines.append(f"[Truncated: {len(rows) - _DB_ROW_CAP} rows omitted]")
            break
        line = " | ".join(str(row[c]) for c in cols)
        total_chars += len(line) + 1
        if total_chars > _DB_CHAR_CAP:
            lines.append(f"[Truncated: {len(rows) - i} rows omitted]")
            break
        lines.append(line)
    return "\n".join(lines)


def _tool_search_scryfall(query: str, scryfall: _ScryfallSearchClient) -> str:
    try:
        results = scryfall.search(query, max_results=100)
    except requests.exceptions.HTTPError as e:
        return f"Scryfall error: {e}"
    if not results:
        return "No results found"
    lines = []
    for card in results:
        lines.append(f"{card['name']} | {card['type_line']} | {card['mana_cost']} | CMC {card['cmc']}")
    return "\n".join(lines)


# ── Agent tools ───────────────────────────────────────────────────────

def _build_tools(conn: sqlite3.Connection) -> list[dict]:
    ddl_parts = []
    for table in _AGENT_TABLES:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if row:
            ddl_parts.append(row[0] + ";")
    schema_ddl = "\n\n".join(ddl_parts)

    query_tool = {
        "name": "query_local_db",
        "description": (
            "Run a read-only SELECT query against the local card database.\n\n"
            f"Schema:\n\n{schema_ddl}\n\n"
            + _QUERY_TOOL_NOTES
        ),
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

    scryfall_tool = {
        "name": "search_scryfall",
        "description": (
            "Search the Scryfall card database.\n\n"
            + _SCRYFALL_TOOL_NOTES
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Scryfall search query string",
                }
            },
            "required": ["query"],
        },
    }

    return [query_tool, scryfall_tool]


# ── System prompt ─────────────────────────────────────────────────────

def _build_system_prompt(
    commander: dict, classified: dict[str, list[dict]]
) -> str:
    ci = json.loads(commander["color_identity"]) if isinstance(commander["color_identity"], str) else commander["color_identity"]

    parts = [
        "You are an expert Magic: The Gathering Commander deck builder.",
        "You are NOT interactive. Do not address the user or ask questions.",
        "Just reason concisely and call tools when needed.",
        "",
        "## Commander",
        f"Name: {commander['name']}",
        f"Mana Cost: {commander.get('mana_cost', 'N/A')}",
        f"Type: {commander.get('type_line', 'N/A')}",
        f"Text: {commander.get('oracle_text', 'N/A')}",
        f"Color Identity: {', '.join(ci) if ci else 'Colorless'}",
        f"CMC: {commander.get('cmc', 'N/A')}",
        "",
        DECK_TEMPLATE,
        "",
        "## Your Task",
        "",
        "Build a 99-card Commander deck from the OWNED cards listed below.",
        "Every card you select MUST have a valid collection_id from the lists.",
        "",
        "Steps:",
        "1. Analyze the commander's strategy and synergies",
        "2. Select cards from each category to meet template targets",
        "3. Use tools to find tribal synergies, combos, or specific effects if needed",
        "4. Verify mana curve matches targets",
        "5. Output exactly 99 cards",
        "",
        "Rules:",
        "- Every card needs a valid collection_id from the pre-classified lists",
        "- Exactly 99 cards total (commander is separate)",
        "- One copy per card (except basic lands)",
        "- Cards can fill multiple roles — count them toward each category they serve",
        "- Report any unfilled template slots as a shopping_list",
        "- Prefer cards with lower EDHREC rank (more popular = more proven)",
        "",
    ]

    # Add classified card lists
    for category, cards in classified.items():
        if not cards:
            continue
        parts.append(f"## Available: {category} ({len(cards)} cards)")
        parts.append("")
        for card in cards[:80]:  # Cap display to avoid token bloat
            rank = card.get("edhrec_rank", "N/A")
            parts.append(
                f"- [{card['collection_id']}] {card['name']} "
                f"({card.get('mana_cost', '')}, CMC {card.get('cmc', '?')}) "
                f"EDHREC#{rank}"
            )
        if len(cards) > 80:
            parts.append(f"  ... and {len(cards) - 80} more (use query_local_db to browse)")
        parts.append("")

    return "\n".join(parts)


# ── Output schema ────────────────────────────────────────────────────

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "deck_name": {"type": "string"},
        "strategy_summary": {"type": "string"},
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "collection_id": {"type": "integer"},
                    "name": {"type": "string"},
                    "categories": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["collection_id", "name", "categories"],
                "additionalProperties": False,
            },
        },
        "shopping_list": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "category": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["name", "category", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["deck_name", "strategy_summary", "cards", "shopping_list"],
    "additionalProperties": False,
}


# ── Trace helper ──────────────────────────────────────────────────────

def _trace(msg: str, status_callback, trace_lines: list[str] | None = None) -> None:
    if trace_lines is not None:
        trace_lines.append(msg)
    if status_callback:
        status_callback(msg)
    else:
        print(msg, file=sys.stderr)


# ── Main entry point ─────────────────────────────────────────────────

def run_deck_builder(
    commander_name: str,
    conn: sqlite3.Connection,
    max_calls: int = DEFAULT_MAX_CALLS,
    status_callback=None,
    trace_out: list[str] | None = None,
    save_deck: bool = True,
) -> dict:
    """Build a 99-card Commander deck from the user's owned collection.

    Args:
        commander_name: Name of the legendary creature to use as commander.
        conn: SQLite connection to the collection database.
        max_calls: Maximum agent tool calls before forcing output.
        status_callback: Optional callable for progress messages.
        trace_out: Optional list to accumulate trace lines.
        save_deck: Whether to persist the deck to the database.

    Returns:
        dict with keys: deck_id, deck_name, strategy, cards, shopping_list, trace, usage
    """
    conn.row_factory = sqlite3.Row
    trace_lines: list[str] = trace_out if trace_out is not None else []

    # 1. Resolve commander
    _trace(f"[DECK] Resolving commander: {commander_name}", status_callback, trace_lines)
    commander = conn.execute(
        "SELECT * FROM cards WHERE name = ? COLLATE NOCASE",
        (commander_name,),
    ).fetchone()
    if not commander:
        raise ValueError(
            f"Commander '{commander_name}' not found in local DB. "
            f"Run 'mtg cache all' to populate the card database."
        )
    commander = dict(commander)

    # Verify it's a legendary creature
    type_line = commander.get("type_line") or ""
    if "Legendary" not in type_line:
        raise ValueError(f"'{commander_name}' is not a Legendary creature: {type_line}")

    # 2. Find in collection
    owned = conn.execute(
        """SELECT c.id FROM collection c
           JOIN printings p ON c.printing_id = p.printing_id
           WHERE p.oracle_id = ? AND c.status = 'owned'
                 AND c.deck_id IS NULL AND c.binder_id IS NULL
           LIMIT 1""",
        (commander["oracle_id"],),
    ).fetchone()
    if not owned:
        raise ValueError(
            f"Commander '{commander_name}' is not in your collection "
            f"(or is already assigned to a deck/binder)."
        )
    commander_collection_id = owned["id"]

    # 3. Extract color identity
    ci_raw = commander.get("color_identity", "[]")
    ci = json.loads(ci_raw) if isinstance(ci_raw, str) else ci_raw
    _trace(f"[DECK] Color identity: {ci}", status_callback, trace_lines)

    # 4. Pre-classify owned cards
    _trace("[DECK] Pre-classifying owned cards...", status_callback, trace_lines)
    classified = classify_owned_cards(conn, ci, commander["oracle_id"], status_callback)
    total = sum(len(v) for v in classified.values())
    for cat, cards in classified.items():
        _trace(f"[DECK]   {cat}: {len(cards)} cards", status_callback, trace_lines)
    _trace(f"[DECK] Total eligible: {total}", status_callback, trace_lines)

    # 5. Build system prompt
    system_text = _build_system_prompt(commander, classified)
    system_content = [
        {"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}
    ]

    # 6. Agent loop
    client = anthropic.Anthropic(
        timeout=httpx.Timeout(600.0, connect=10.0),
    )
    tools = _build_tools(conn)
    scryfall = _ScryfallSearchClient()
    usage: dict[str, dict[str, int]] = {
        "sonnet": {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0},
    }

    messages = [{"role": "user", "content": "Build the Commander deck now."}]
    tool_call_count = 0
    response = None

    _trace(f"[DECK] Starting agent loop (max_calls={max_calls})", status_callback, trace_lines)

    while tool_call_count < max_calls:
        response = client.messages.create(
            model=AGENT_MODEL,
            max_tokens=8000,
            temperature=0,
            system=system_content,
            tools=tools,
            messages=messages,
        )

        usage["sonnet"]["input"] += response.usage.input_tokens
        usage["sonnet"]["output"] += response.usage.output_tokens
        usage["sonnet"]["cache_read"] += getattr(response.usage, "cache_read_input_tokens", 0) or 0
        usage["sonnet"]["cache_creation"] += getattr(response.usage, "cache_creation_input_tokens", 0) or 0

        for block in response.content:
            if block.type == "text":
                _trace(f"[AGENT] {block.text.strip()}", status_callback, trace_lines)
            elif block.type == "tool_use":
                _trace(f"[TOOL CALL] {block.name}: {json.dumps(block.input)[:200]}", status_callback, trace_lines)

        if response.stop_reason == "end_turn" or not any(b.type == "tool_use" for b in response.content):
            break

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            tool_call_count += 1
            if block.name == "query_local_db":
                result = _tool_query_local_db(block.input.get("sql", ""), conn)
            elif block.name == "search_scryfall":
                result = _tool_search_scryfall(block.input.get("query", ""), scryfall)
            else:
                result = f"Unknown tool: {block.name}"

            _trace(
                f"[TOOL RESULT] {block.name}: {result[:300]}{'...' if len(result) > 300 else ''}",
                status_callback, trace_lines,
            )
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    _trace(f"[DECK] Tool calls used: {tool_call_count}/{max_calls}", status_callback, trace_lines)

    # 7. Final extraction via structured output
    if response is not None and response.stop_reason == "end_turn":
        messages.append({"role": "assistant", "content": response.content})
    messages.append({
        "role": "user",
        "content": "Output the final 99-card decklist now.",
    })

    _trace("[DECK] Requesting structured output...", status_callback, trace_lines)
    final_response = client.messages.create(
        model=AGENT_MODEL,
        max_tokens=8000,
        temperature=0,
        system=system_content,
        messages=messages,
        output_config={
            "format": {
                "type": "json_schema",
                "schema": OUTPUT_SCHEMA,
            }
        },
    )
    usage["sonnet"]["input"] += final_response.usage.input_tokens
    usage["sonnet"]["output"] += final_response.usage.output_tokens
    usage["sonnet"]["cache_read"] += getattr(final_response.usage, "cache_read_input_tokens", 0) or 0
    usage["sonnet"]["cache_creation"] += getattr(final_response.usage, "cache_creation_input_tokens", 0) or 0

    result = json.loads(final_response.content[0].text)
    _trace(f"[DECK] Got {len(result['cards'])} cards, {len(result['shopping_list'])} shopping list items",
           status_callback, trace_lines)

    # 8. Validate
    card_count = len(result["cards"])
    if card_count != 99:
        _trace(f"[DECK] WARNING: Expected 99 cards, got {card_count}", status_callback, trace_lines)

    # Validate collection_ids exist and are available
    all_cids = {c["collection_id"] for c in result["cards"]}
    all_cids.add(commander_collection_id)
    placeholders = ",".join("?" * len(all_cids))
    valid_rows = conn.execute(
        f"SELECT id FROM collection WHERE id IN ({placeholders}) "
        f"AND status = 'owned' AND deck_id IS NULL AND binder_id IS NULL",
        list(all_cids),
    ).fetchall()
    valid_ids = {r["id"] for r in valid_rows}
    invalid = all_cids - valid_ids
    if invalid:
        _trace(f"[DECK] WARNING: {len(invalid)} invalid collection_ids: {sorted(invalid)[:10]}",
               status_callback, trace_lines)

    # Check for duplicate oracle_ids (except basic lands)
    basic_land_names = {"Plains", "Island", "Swamp", "Mountain", "Forest",
                        "Wastes", "Snow-Covered Plains", "Snow-Covered Island",
                        "Snow-Covered Swamp", "Snow-Covered Mountain",
                        "Snow-Covered Forest"}
    seen_names: dict[str, int] = {}
    for card in result["cards"]:
        name = card["name"]
        if name not in basic_land_names:
            if name in seen_names:
                _trace(f"[DECK] WARNING: Duplicate card: {name}", status_callback, trace_lines)
            seen_names[name] = seen_names.get(name, 0) + 1

    # 9. Persist
    deck_id = None
    if save_deck:
        from mtg_collector.db.models import Deck, DeckRepository

        deck_repo = DeckRepository(conn)
        deck = Deck(
            id=None,
            name=result["deck_name"],
            description=result["strategy_summary"],
            format="commander",
        )
        deck_id = deck_repo.add(deck)

        # Assign commander
        deck_repo.add_cards(deck_id, [commander_collection_id], zone="commander")

        # Assign 99 mainboard cards (only valid IDs)
        mainboard_ids = [c["collection_id"] for c in result["cards"]
                         if c["collection_id"] in valid_ids
                         and c["collection_id"] != commander_collection_id]
        if mainboard_ids:
            deck_repo.add_cards(deck_id, mainboard_ids, zone="mainboard")

        conn.commit()
        _trace(f"[DECK] Saved deck #{deck_id}: {result['deck_name']}", status_callback, trace_lines)

    cache_read = usage["sonnet"]["cache_read"]
    cache_creation = usage["sonnet"]["cache_creation"]
    _trace(
        f"[USAGE] sonnet={usage['sonnet']['input']}in/{usage['sonnet']['output']}out "
        f"cache_read={cache_read} cache_creation={cache_creation}",
        status_callback, trace_lines,
    )

    return {
        "deck_id": deck_id,
        "deck_name": result["deck_name"],
        "strategy": result["strategy_summary"],
        "cards": result["cards"],
        "shopping_list": result["shopping_list"],
        "trace": trace_lines,
        "usage": usage,
    }
