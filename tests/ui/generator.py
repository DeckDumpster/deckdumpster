"""
Implementation generator — runs the Claude harness once in recording mode
and emits a deterministic ReplayHarness script.

Usage (via pytest flags, see conftest.py):
    uv run pytest tests/ui/ --generate <intent_name> --instance <instance>
    uv run pytest tests/ui/ --generate-missing --instance <instance>
"""

import ast
import hashlib
import logging
import re
import subprocess
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .harness import UIHarness

log = logging.getLogger(__name__)

INTENTS_DIR = Path(__file__).parent / "intents"
HINTS_DIR = Path(__file__).parent / "hints"
IMPLEMENTATIONS_DIR = Path(__file__).parent / "implementations"

# Maps URL paths to HTML source files for data-testid insertion.
_PAGE_TO_HTML = {
    "/": "index.html",
    "/collection": "collection.html",
    "/sealed": "sealed.html",
    "/recent": "recent.html",
    "/crack-pack": "crack_pack.html",
    "/explore-sheets": "explore_sheets.html",
    "/ingest-ids": "ingest_ids.html",
    "/disambiguate": "disambiguate.html",
    "/orders/": "order_detail.html",
    "/orders": "orders.html",
    "/ingest-corners": "ingest_corners.html",
    "/ingest-order": "ingest_order.html",
    "/decks": "decks.html",
    "/import-csv": "import_csv.html",
    "/binders": "binders.html",
    "/process": "process.html",
    "/upload": "upload.html",
    "/card/": "card_detail.html",
}

STATIC_DIR = Path(__file__).parents[2] / "mtg_collector" / "static"


def _git_sha() -> str:
    """Return the current short git SHA, or 'unknown'."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).parents[2],
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def _intent_hash(intent_path: Path) -> str:
    """SHA-256 of the intent file contents."""
    return hashlib.sha256(intent_path.read_bytes()).hexdigest()[:16]


def _url_path(full_url: str, base_url: str) -> str:
    """Extract the path portion from a full URL relative to base."""
    if full_url.startswith(base_url):
        path = full_url[len(base_url):]
        return path if path else "/"
    return "/"


def _find_html_for_url(page_url: str, base_url: str) -> Path | None:
    """Map a page URL to the HTML source file."""
    path = _url_path(page_url, base_url)
    # Strip query string.
    path = path.split("?")[0]
    filename = _PAGE_TO_HTML.get(path)
    if not filename:
        # Try prefix matching for parameterized routes (e.g. /card/:set/:cn).
        for prefix, fname in _PAGE_TO_HTML.items():
            if prefix.endswith("/") and path.startswith(prefix):
                filename = fname
                break
    if filename:
        html_path = STATIC_DIR / filename
        if html_path.exists():
            return html_path
    return None


def _make_testid(scenario_name: str, step: int, element: dict) -> str:
    """Generate a data-testid value for an element."""
    tag = element.get("tag", "el")
    text = element.get("text", "")
    # Build a readable slug from the text.
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower().strip())[:30].strip("-")
    if slug:
        return f"{tag}-{slug}"
    return f"{scenario_name}-step{step}-{tag}"


def _add_testid_to_html(html_path: Path, element: dict, testid: str) -> bool:
    """Add data-testid attribute to the element in the HTML source.

    Tries to find the element by id, then by tag+text pattern.
    Returns True if the attribute was added.
    """
    content = html_path.read_text()
    tag = element.get("tag", "")
    el_id = element.get("id")
    text = element.get("text", "")

    # Already has this testid?
    if f'data-testid="{testid}"' in content:
        return True

    # Strategy 1: find by id attribute.
    if el_id:
        pattern = f'id="{el_id}"'
        if pattern in content:
            new = f'id="{el_id}" data-testid="{testid}"'
            content = content.replace(pattern, new, 1)
            html_path.write_text(content)
            log.info("Added data-testid=\"%s\" to %s (by id=%s)", testid, html_path.name, el_id)
            return True

    # Strategy 2: find opening tag with matching text nearby.
    # Look for <tag ...>text patterns.
    if text and tag:
        # Escape for regex.
        escaped_text = re.escape(text[:40])
        pattern = re.compile(
            rf"(<{tag}\b[^>]*>)\s*{escaped_text}",
            re.IGNORECASE,
        )
        match = pattern.search(content)
        if match:
            opening_tag = match.group(1)
            if "data-testid" not in opening_tag:
                new_tag = opening_tag[:-1] + f' data-testid="{testid}">'
                content = content.replace(opening_tag, new_tag, 1)
                html_path.write_text(content)
                log.info(
                    "Added data-testid=\"%s\" to %s (by tag=%s text=%s)",
                    testid, html_path.name, tag, text[:30],
                )
                return True

    log.warning(
        "Could not add data-testid=\"%s\" to %s — element not found in source",
        testid, html_path.name,
    )
    return False


def _escape_for_python(value: str) -> str:
    """Escape a string for use in a Python string literal.

    Also truncates multiline innerText to the first meaningful line,
    since innerText often includes child element text.
    """
    # Take only the first line of multiline text.
    first_line = value.split("\n")[0].strip()
    return first_line.replace("\\", "\\\\").replace('"', '\\"')


def _translate_step(step: dict, scenario_name: str, base_url: str) -> str | None:
    """Translate a recorded harness step into a ReplayHarness call."""
    action = step["action"]
    inputs = step["input"]
    selector_info = step.get("stable_selector")

    if action == "navigate":
        path = _escape_for_python(inputs["path"])
        return f'    harness.navigate("{path}")'

    if action == "scroll":
        direction = inputs["direction"]
        return f'    harness.scroll("{direction}")'

    if action == "click":
        if not selector_info:
            return f"    # WARNING: no stable selector for click step {step['step']}"
        strategy, value = selector_info
        escaped = _escape_for_python(value)
        if strategy == "test_id":
            return f'    harness.click_by_test_id("{escaped}")'
        if strategy == "text":
            return f'    harness.click_by_text("{escaped}")'
        if strategy == "aria_label":
            return f'    harness.click_by_selector(\'[aria-label="{escaped}"]\')'
        if strategy == "placeholder":
            return f'    harness.click_by_selector(\'[placeholder="{escaped}"]\')'
        return f'    harness.click_by_selector("{escaped}")'

    if action == "fill":
        value = _escape_for_python(inputs["value"])
        if not selector_info:
            return f"    # WARNING: no stable selector for fill step {step['step']}"
        strategy, sel_value = selector_info
        escaped = _escape_for_python(sel_value)
        if strategy == "placeholder":
            return f'    harness.fill_by_placeholder("{escaped}", "{value}")'
        if strategy == "test_id":
            return f'    harness.fill_by_selector(\'[data-testid="{escaped}"]\', "{value}")'
        return f'    harness.fill_by_selector("{escaped}", "{value}")'

    if action == "select_option":
        label = _escape_for_python(inputs["label"])
        if not selector_info:
            return f"    # WARNING: no stable selector for select step {step['step']}"
        strategy, sel_value = selector_info
        escaped = _escape_for_python(sel_value)
        if strategy == "test_id":
            return f'    harness.select_by_label(\'[data-testid="{escaped}"]\', "{label}")'
        if strategy == "selector":
            return f'    harness.select_by_label("{escaped}", "{label}")'
        # text/placeholder/aria_label are not valid CSS selectors for <select> —
        # fall back to the element's CSS path if available.
        element_idx = inputs.get("element")
        elements = step.get("elements_snapshot", [])
        el = next((e for e in elements if e["idx"] == element_idx), None)
        if el and el.get("css_path"):
            css = _escape_for_python(el["css_path"])
            return f'    harness.select_by_label("{css}", "{label}")'
        return f"    # WARNING: no CSS selector for select step {step['step']} (strategy={strategy})"

    if action == "press_key":
        key = _escape_for_python(inputs["key"])
        if selector_info and "element" in inputs:
            strategy, sel_value = selector_info
            escaped = _escape_for_python(sel_value)
            if strategy == "placeholder":
                # Use the placeholder selector for targeting
                return f'    harness.press_key("{key}", selector=\'[placeholder="{escaped}"]\')'
            if strategy == "test_id":
                return f'    harness.press_key("{key}", selector=\'[data-testid="{escaped}"]\')'
            if strategy == "selector":
                return f'    harness.press_key("{key}", selector="{escaped}")'
        return f'    harness.press_key("{key}")'

    return None


def _load_hints(intent_path: Path) -> dict | None:
    """Load hints for an intent if they exist."""
    rel = intent_path.relative_to(INTENTS_DIR)
    hints_path = HINTS_DIR / rel
    if hints_path.exists():
        hints = yaml.safe_load(hints_path.read_text())
        log.info("Loaded hints from: %s", hints_path)
        return hints
    return None


def generate(
    intent_path: Path,
    page,
    base_url: str,
    screenshot_dir: Path,
) -> Path:
    """Run the harness in recording mode and emit an implementation module.

    Returns the path to the generated implementation file.
    """
    scenario_name = intent_path.stem
    intent = yaml.safe_load(intent_path.read_text())
    goal = intent["description"]
    hints = _load_hints(intent_path)

    log.info("Generating implementation for intent: %s", scenario_name)

    # Run the harness in recording mode.
    harness = UIHarness(
        page, base_url, screenshot_dir, scenario_name,
        recording=True, hints=hints,
    )
    # Generation is a one-time cost — allow more steps than normal replay.
    result = harness.run(goal, max_steps=35)

    if result["status"] != "done":
        raise RuntimeError(
            f"Harness failed for {scenario_name}: {result.get('reason', 'unknown')}"
        )

    # Translate recorded steps into ReplayHarness calls.
    # Also detect async element appearances (modals, overlays) between steps
    # and emit wait_for_visible calls.
    lines = []
    prev_elements = None
    for step in result["steps"]:
        selector_info = step.get("stable_selector")
        cur_elements = step.get("elements_snapshot", [])

        # Detect async elements that appeared since the previous step.
        # Look for modals/overlays that just became visible.
        if prev_elements is not None:
            prev_ids = {e.get("id") for e in prev_elements if e.get("id")}
            for el in cur_elements:
                el_id = el.get("id", "")
                if not el_id:
                    continue
                # Detect modal/overlay elements that are new.
                is_async_el = any(
                    kw in el_id.lower()
                    for kw in ("modal", "overlay", "dialog", "popup")
                )
                if is_async_el and el_id not in prev_ids:
                    lines.append(f'    harness.wait_for_visible("#{el_id}", timeout=10_000)')
        prev_elements = cur_elements

        # If the stable selector fell back to data-uitest (ephemeral), try to
        # add a data-testid to the HTML source.
        if selector_info and selector_info[0] == "selector" and "data-uitest" in selector_info[1]:
            element_idx = step["input"].get("element")
            elements = step.get("elements_snapshot", [])
            el = next((e for e in elements if e["idx"] == element_idx), None)
            if el:
                page_url = step.get("page_url", "")
                html_path = _find_html_for_url(page_url, base_url)
                if html_path:
                    testid = _make_testid(scenario_name, step["step"], el)
                    if _add_testid_to_html(html_path, el, testid):
                        step["stable_selector"] = ("test_id", testid)

        line = _translate_step(step, scenario_name, base_url)
        if line:
            lines.append(line)

    # Add a final screenshot.
    lines.append('    harness.screenshot("final_state")')

    # Build the module.
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sha = _git_sha()
    ihash = _intent_hash(intent_path)

    module_content = textwrap.dedent(f'''\
        """
        Generated from intent: {scenario_name}
        Generated at: {timestamp}
        System version: {sha}
        Intent hash: {ihash}
        """


        def steps(harness):
    ''')
    module_content += "\n".join(lines) + "\n"

    # Validate generated Python before writing.
    try:
        ast.parse(module_content, filename=scenario_name)
    except SyntaxError as e:
        log.error(
            "Generated code has syntax error at line %d: %s\n%s",
            e.lineno, e.msg, module_content,
        )
        raise RuntimeError(
            f"Generated implementation for {scenario_name} has a syntax error "
            f"at line {e.lineno}: {e.msg}"
        ) from e

    # Write the implementation file, mirroring the intent directory structure.
    rel = intent_path.relative_to(INTENTS_DIR).with_suffix(".py")
    impl_path = IMPLEMENTATIONS_DIR / rel

    # Ensure parent directories exist with __init__.py.
    impl_path.parent.mkdir(parents=True, exist_ok=True)
    init_file = impl_path.parent / "__init__.py"
    if not init_file.exists():
        init_file.touch()

    impl_path.write_text(module_content)
    log.info("Generated implementation: %s", impl_path)

    return impl_path
