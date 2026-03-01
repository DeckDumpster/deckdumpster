"""
UI testing harness — Claude Vision agent loop.

Drives a Playwright browser by sending screenshots + interactive element lists
to Claude, which decides the next action at each step.  Continues until Claude
declares the goal achieved (``done``) or unachievable (``fail``), or the step
limit is hit.

Screenshots are saved after every action:
``{scenario}_{step:02d}_{label}.png``
"""

import base64
import json
import logging
import os
from pathlib import Path

import anthropic

log = logging.getLogger(__name__)

MODEL = os.environ.get("UI_TEST_MODEL", "claude-sonnet-4-6")
MAX_STEPS = 20

SYSTEM = """\
You are a UI testing agent. You interact with a web application to accomplish \
a goal by choosing browser actions one at a time.

Each turn you receive:
1. A screenshot of the current page
2. A numbered list of interactive elements visible on the page

Rules:
- Choose ONE action per turn using the provided tools.
- Refer to elements by their index number from the elements list.
- After filling an input, the page may update asynchronously (debounce). \
Check the next screenshot before acting on results.
- Use 'done' ONLY after you can visually confirm the goal is fully achieved.
- Use 'fail' if the goal clearly cannot be accomplished.
- Be methodical — don't skip steps or assume state you can't see.\
"""

TOOLS = [
    {
        "name": "navigate",
        "description": "Go to a URL path on the site.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "URL path, e.g. /sealed or /collection",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "click",
        "description": "Click an interactive element.",
        "input_schema": {
            "type": "object",
            "properties": {
                "element": {
                    "type": "integer",
                    "description": "Element index from the list",
                },
            },
            "required": ["element"],
        },
    },
    {
        "name": "fill",
        "description": "Clear an input field and type new text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "element": {
                    "type": "integer",
                    "description": "Element index (must be an input/textarea)",
                },
                "value": {
                    "type": "string",
                    "description": "Text to type",
                },
            },
            "required": ["element", "value"],
        },
    },
    {
        "name": "select_option",
        "description": "Choose an option from a <select> dropdown.",
        "input_schema": {
            "type": "object",
            "properties": {
                "element": {
                    "type": "integer",
                    "description": "Element index (must be a <select>)",
                },
                "label": {
                    "type": "string",
                    "description": "Visible text of the option to select",
                },
            },
            "required": ["element", "label"],
        },
    },
    {
        "name": "scroll",
        "description": "Scroll the page up or down.",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["up", "down"],
                },
            },
            "required": ["direction"],
        },
    },
    {
        "name": "done",
        "description": "The goal has been visually confirmed as achieved.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "What was accomplished",
                },
            },
            "required": ["summary"],
        },
    },
    {
        "name": "fail",
        "description": "The goal cannot be achieved.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why the goal is unachievable",
                },
            },
            "required": ["reason"],
        },
    },
]

# Injected into the page to enumerate visible interactive elements and tag
# each one with data-uitest="N" so the harness can target them reliably.
EXTRACT_ELEMENTS_JS = """
(() => {
  document.querySelectorAll('[data-uitest]').forEach(
    el => el.removeAttribute('data-uitest')
  );

  const sels = [
    'button', 'a[href]', 'input', 'select', 'textarea',
    '[role="button"]', '[role="link"]', '[role="tab"]',
    '[role="checkbox"]', '[role="radio"]', 'summary',
    '[onclick]', '[tabindex]:not([tabindex="-1"])',
  ].join(', ');

  const results = [];
  let idx = 0;

  const vw = window.innerWidth;
  const vh = window.innerHeight;

  function tag(el) {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) return;
    if (rect.right < 0 || rect.left > vw || rect.bottom < 0 || rect.top > vh) return;
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return;

    el.setAttribute('data-uitest', String(idx));

    let value = null;
    if (el.tagName === 'SELECT' && el.selectedOptions.length)
      value = el.selectedOptions[0].text;
    else if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')
      value = (el.value || '').slice(0, 50) || null;

    // Build a CSS selector path for fallback targeting.
    function cssPath(e) {
      const parts = [];
      while (e && e.nodeType === 1) {
        let sel = e.tagName.toLowerCase();
        if (e.id) { parts.unshift('#' + e.id); break; }
        const sib = e.parentElement ? Array.from(e.parentElement.children).filter(
          c => c.tagName === e.tagName) : [];
        if (sib.length > 1) sel += ':nth-of-type(' + (sib.indexOf(e) + 1) + ')';
        parts.unshift(sel);
        e = e.parentElement;
      }
      return parts.join(' > ');
    }

    results.push({
      idx: idx,
      tag: el.tagName.toLowerCase(),
      text: (el.innerText || '').trim().slice(0, 80) || null,
      type: el.type || null,
      placeholder: el.placeholder || null,
      id: el.id || null,
      value: value,
      disabled: el.disabled || false,
      testid: el.getAttribute('data-testid') || null,
      aria_label: el.getAttribute('aria-label') || null,
      css_path: cssPath(el),
    });
    idx++;
  }

  // Pass 1: standard interactive elements.
  for (const el of document.querySelectorAll(sels)) tag(el);

  // Pass 2: elements with cursor:pointer that weren't already tagged
  // (catches dynamically-rendered list items with JS click handlers).
  for (const el of document.querySelectorAll('li, div, span, tr, td')) {
    if (el.hasAttribute('data-uitest')) continue;
    if (el.querySelector('[data-uitest]')) continue;  // skip parents of tagged children
    const style = getComputedStyle(el);
    if (style.cursor !== 'pointer') continue;
    tag(el);
  }

  return results;
})()
"""


class UIHarness:
    """Drive a Playwright page toward a UX goal via Claude Vision agent loop."""

    def __init__(self, page, base_url: str, screenshot_dir: Path, scenario_name: str,
                 *, recording: bool = False, hints: dict | None = None):
        self.page = page
        self.base_url = base_url
        self.screenshot_dir = screenshot_dir
        self.scenario_name = scenario_name
        self.recording = recording
        self.hints = hints
        self.client = anthropic.Anthropic()
        self._step = 0
        self._history: list[dict] = []
        self._messages: list[dict] = []
        self._pending_tool_results: list[dict] = []
        self._last_elements: list[dict] = []

    # ── public API ────────────────────────────────────────────────────────

    def run(self, goal: str, max_steps: int = MAX_STEPS) -> dict:
        """Run the agent loop.  Returns ``{status, summary|reason, steps}``."""
        # Build augmented goal with hints if available.
        augmented_goal = goal
        if self.hints:
            hint_parts = []
            if self.hints.get("start_page"):
                hint_parts.append(f"Start on page: {self.hints['start_page']}")
            if self.hints.get("involves"):
                involves = ", ".join(self.hints["involves"])
                hint_parts.append(f"Key UI elements: {involves}")
            if self.hints.get("fixture_data"):
                data_items = [f"{k}={v}" for k, v in self.hints["fixture_data"].items()]
                hint_parts.append(f"Test data to use: {', '.join(data_items)}")
            if self.hints.get("notes"):
                hint_parts.append(f"Notes: {self.hints['notes']}")
            if hint_parts:
                augmented_goal = goal + "\n\nHints:\n" + "\n".join(f"- {h}" for h in hint_parts)

        log.info("[%s] Goal: %s", self.scenario_name, augmented_goal.strip()[:200])

        # Auto-accept JS dialogs (confirm/alert) and provide a default for prompt().
        self._last_dialog_message = None
        def _handle_dialog(dialog):
            self._last_dialog_message = dialog.message
            if dialog.type == "prompt":
                dialog.accept(dialog.default_value or "Test View")
            else:
                dialog.accept()
        self.page.on("dialog", _handle_dialog)

        # Navigate to start page (from hints) or homepage.
        start = "/"
        if self.hints and self.hints.get("start_page"):
            start = self.hints["start_page"]
        self.page.goto(f"{self.base_url}{start}", wait_until="networkidle")

        for _ in range(max_steps):
            screenshot_b64, elements = self._observe()
            log.info(
                "[%s] Step %d — %d interactive elements visible",
                self.scenario_name, self._step, len(elements),
            )
            action = self._decide(augmented_goal, screenshot_b64, elements)

            name = action["name"]
            inputs = action["input"]

            if name == "done":
                log.info("[%s] DONE: %s", self.scenario_name, inputs["summary"])
                self._snap("done")
                result = {
                    "status": "done",
                    "summary": inputs["summary"],
                    "steps": self._history,
                }
                if self.recording:
                    result["done_summary"] = inputs["summary"]
                    result["final_elements"] = self._last_elements
                    result["final_url"] = self.page.url
                return result

            if name == "fail":
                log.warning("[%s] FAIL: %s", self.scenario_name, inputs["reason"])
                self._snap("fail")
                return {
                    "status": "fail",
                    "reason": inputs["reason"],
                    "steps": self._history,
                }

            log.info(
                "[%s] Step %d → %s(%s)",
                self.scenario_name, self._step, name, json.dumps(inputs),
            )
            result = self._execute(name, inputs)
            log.info("[%s] Step %d result: %s", self.scenario_name, self._step, result)
            entry = {
                "step": self._step,
                "action": name,
                "input": inputs,
                "result": result,
            }
            if self.recording:
                element_idx = inputs.get("element")
                entry["stable_selector"] = (
                    self._stable_selector(element_idx)
                    if element_idx is not None else None
                )
                entry["elements_snapshot"] = self._last_elements
                entry["page_url"] = self.page.url
            self._history.append(entry)
            self._settle()

        self._snap("max_steps")
        log.warning("[%s] Exceeded %d steps", self.scenario_name, max_steps)
        return {
            "status": "fail",
            "reason": f"Exceeded {max_steps} steps",
            "steps": self._history,
        }

    # ── internals ─────────────────────────────────────────────────────────

    def _observe(self):
        """Screenshot the page and extract interactive elements."""
        self._step += 1
        path = self._snap(f"step_{self._step:02d}")
        screenshot_b64 = base64.standard_b64encode(path.read_bytes()).decode()
        elements = self.page.evaluate(EXTRACT_ELEMENTS_JS)
        self._last_elements = elements
        return screenshot_b64, elements

    def _decide(self, goal, screenshot_b64, elements):
        """Send current state to Claude and get back a tool-use action."""
        elements_text = self._format_elements(elements)

        user_content = []

        # Include pending tool_result(s) from previous turn.
        if self._pending_tool_results:
            user_content.extend(self._pending_tool_results)
            self._pending_tool_results = []

        user_content.append({
            "type": "text",
            "text": (
                f"Goal: {goal}\n\n"
                f"Current page elements:\n{elements_text}"
            ) if not self._messages else (
                f"Current page elements:\n{elements_text}"
            ),
        })
        user_content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": screenshot_b64,
            },
        })

        self._messages.append({"role": "user", "content": user_content})

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM,
            tools=TOOLS,
            messages=self._messages,
        )

        # Append the full assistant response to maintain conversation history.
        self._messages.append({"role": "assistant", "content": response.content})

        # Log any reasoning text before the tool call.
        reasoning = "".join(b.text for b in response.content if b.type == "text")
        if reasoning:
            log.info("[%s] Reasoning: %s", self.scenario_name, reasoning.strip()[:200])

        # Collect tool_results for ALL tool_use blocks in this response.
        # The API requires every tool_use to have a matching tool_result.
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if tool_uses:
            # Stash results for all tool_uses — execute only the first.
            self._pending_tool_results = [
                {"type": "tool_result", "tool_use_id": b.id, "content": "OK"}
                for b in tool_uses
            ]
            first = tool_uses[0]
            return {"name": first.name, "input": first.input}

        # No tool call — treat as failure.
        return {"name": "fail", "input": {"reason": f"No action chosen: {reasoning[:200]}"}}

    def _execute(self, action, inputs):
        """Dispatch an action to Playwright.  Returns a short result string."""
        # Re-tag elements right before acting — DOM may have re-rendered
        # since _observe() (e.g. async search results replacing innerHTML).
        self.page.evaluate(EXTRACT_ELEMENTS_JS)

        timeout = 5_000  # 5s max per action
        try:
            if action == "navigate":
                self.page.goto(
                    f"{self.base_url}{inputs['path']}",
                    wait_until="networkidle", timeout=timeout,
                )
                return "navigated"

            if action == "click":
                selector = f'[data-uitest="{inputs["element"]}"]'
                self.page.click(selector, timeout=timeout)
                return "clicked"

            if action == "fill":
                selector = f'[data-uitest="{inputs["element"]}"]'
                self.page.fill(selector, inputs["value"], timeout=timeout)
                return "filled"

            if action == "select_option":
                selector = f'[data-uitest="{inputs["element"]}"]'
                self.page.select_option(selector, label=inputs["label"], timeout=timeout)
                return "selected"

            if action == "scroll":
                delta = -500 if inputs["direction"] == "up" else 500
                self.page.mouse.wheel(0, delta)
                return "scrolled"

            return f"unknown action: {action}"
        except Exception as e:
            return f"error: {e}"

    def _settle(self):
        """Wait briefly for async page updates to land."""
        self.page.wait_for_timeout(500)
        try:
            self.page.wait_for_load_state("networkidle", timeout=3000)
        except Exception:
            pass

    def _snap(self, label: str) -> Path:
        """Take a viewport screenshot and return the file path."""
        name = f"{self.scenario_name}_{self._step:02d}_{label}.png"
        path = self.screenshot_dir / name
        self.page.screenshot(path=str(path))
        return path

    def _stable_selector(self, idx):
        """Return the best stable selector for an element by index.

        Returns a tuple of (strategy, value) where strategy is one of:
        test_id, text, placeholder, selector.
        """
        el = next((e for e in self._last_elements if e["idx"] == idx), None)
        if el is None:
            return ("selector", f'[data-uitest="{idx}"]')

        if el.get("testid"):
            return ("test_id", el["testid"])

        # Unique text — only usable if no other visible element has the same text.
        text = el.get("text")
        if text:
            same_text = [e for e in self._last_elements if e.get("text") == text]
            if len(same_text) == 1:
                return ("text", text)

        if el.get("placeholder"):
            return ("placeholder", el["placeholder"])

        if el.get("id"):
            return ("selector", f'#{el["id"]}')

        if el.get("aria_label"):
            return ("aria_label", el["aria_label"])

        if el.get("css_path"):
            return ("selector", el["css_path"])

        return ("selector", f'[data-uitest="{idx}"]')

    @staticmethod
    def _format_elements(elements):
        lines = []
        for el in elements:
            parts = [f"[{el['idx']}]", el["tag"]]
            if el.get("id"):
                parts.append(f"#{el['id']}")
            if el.get("type"):
                parts.append(f"type={el['type']}")
            if el.get("text"):
                parts.append(f'"{el["text"]}"')
            if el.get("placeholder"):
                parts.append(f'placeholder="{el["placeholder"]}"')
            if el.get("value"):
                parts.append(f'value="{el["value"]}"')
            if el.get("disabled"):
                parts.append("(disabled)")
            lines.append(" ".join(parts))
        return "\n".join(lines)

