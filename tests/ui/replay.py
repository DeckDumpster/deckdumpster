"""
Deterministic UI test replay — Playwright wrapper with zero Claude calls.

Executes generated implementation scripts against a live instance using
stable selectors (text, placeholder, test ID, CSS).  Every action captures
a screenshot and DOM snapshot for evidence.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .harness import EXTRACT_ELEMENTS_JS

log = logging.getLogger(__name__)


@dataclass
class ReplayStep:
    number: int
    action: str
    detail: str
    screenshot: str | None = None
    dom_snapshot: list | None = None
    error: str | None = None


class ReplayStepError(Exception):
    """Raised when a replay step fails."""

    def __init__(self, step: ReplayStep):
        self.step = step
        super().__init__(
            f"Step {step.number} ({step.action}: {step.detail}) failed: {step.error}"
        )


@dataclass
class ReplayResult:
    intent: str
    status: str  # "done" or "fail"
    steps: list[ReplayStep] = field(default_factory=list)
    failure_step: int | None = None
    error: str | None = None


class ReplayHarness:
    """Execute a generated implementation with zero Claude calls."""

    def __init__(self, page, base_url: str, screenshot_dir: Path, scenario_name: str):
        self.page = page
        self.base_url = base_url
        self.screenshot_dir = screenshot_dir
        self.scenario_name = scenario_name
        self._step = 0
        self._steps: list[ReplayStep] = []

    # ── Navigation ─────────────────────────────────────────────────────

    def navigate(self, path: str):
        self._record("navigate", path)
        self.page.goto(
            f"{self.base_url}{path}", wait_until="networkidle", timeout=5_000
        )
        self._settle()
        self._snap()

    # ── Interaction ────────────────────────────────────────────────────

    def click_by_text(self, text: str, *, exact: bool = False):
        self._record("click_by_text", text)
        self.page.get_by_text(text, exact=exact).first.click(timeout=500)
        self._settle()
        self._snap()

    def click_by_selector(self, selector: str):
        self._record("click_by_selector", selector)
        self.page.click(selector, timeout=500)
        self._settle()
        self._snap()

    def click_by_test_id(self, test_id: str):
        self._record("click_by_test_id", test_id)
        self.page.get_by_test_id(test_id).click(timeout=500)
        self._settle()
        self._snap()

    def fill_by_placeholder(self, placeholder: str, value: str):
        self._record("fill_by_placeholder", f"{placeholder}={value}")
        self.page.get_by_placeholder(placeholder).fill(value, timeout=500)
        self._settle()
        self._snap()

    def fill_by_selector(self, selector: str, value: str):
        self._record("fill_by_selector", f"{selector}={value}")
        self.page.fill(selector, value, timeout=500)
        self._settle()
        self._snap()

    def press_key(self, key: str, *, selector: str | None = None):
        """Press a keyboard key, optionally targeting a specific element."""
        target = selector or "active element"
        self._record("press_key", f"{key} on {target}")
        if selector:
            self.page.press(selector, key, timeout=500)
        else:
            self.page.keyboard.press(key)
        self._settle()
        self._snap()

    def set_input_files(self, selector: str, file_path: str):
        self._record("set_input_files", f"{selector} <- {file_path}")
        self.page.set_input_files(selector, file_path, timeout=500)
        self._settle()
        self._snap()

    def select_by_label(self, selector: str, label: str):
        self._record("select_by_label", f"{selector}={label}")
        self.page.select_option(selector, label=label, timeout=500)
        self._settle()
        self._snap()

    def scroll(self, direction: str):
        self._record("scroll", direction)
        delta = -500 if direction == "up" else 500
        self.page.mouse.wheel(0, delta)
        self._settle()
        self._snap()

    # ── Waiting ────────────────────────────────────────────────────────

    def wait_for_visible(self, selector: str, timeout: int = 500):
        self._record("wait_for_visible", selector)
        self.page.wait_for_selector(selector, state="visible", timeout=timeout)
        self._snap()

    def wait_for_hidden(self, selector: str, timeout: int = 500):
        self._record("wait_for_hidden", selector)
        self.page.wait_for_selector(selector, state="hidden", timeout=timeout)
        self._snap()

    def wait_for_text(self, text: str, timeout: int = 500):
        self._record("wait_for_text", text)
        self.page.get_by_text(text).first.wait_for(state="visible", timeout=timeout)
        self._snap()

    # ── Assertions ─────────────────────────────────────────────────────

    def assert_visible(self, selector: str):
        self._record("assert_visible", selector)
        visible = self.page.is_visible(selector, timeout=500)
        if not visible:
            self._fail(f"Expected visible: {selector}")
        self._snap()

    def assert_hidden(self, selector: str):
        self._record("assert_hidden", selector)
        hidden = self.page.is_hidden(selector, timeout=500)
        if not hidden:
            self._fail(f"Expected hidden: {selector}")
        self._snap()

    def assert_text_present(self, text: str):
        self._record("assert_text_present", text)
        count = self.page.get_by_text(text).count()
        if count == 0:
            self._fail(f"Expected text present: {text}")
        self._snap()

    def assert_text_absent(self, text: str):
        self._record("assert_text_absent", text)
        count = self.page.get_by_text(text).count()
        if count > 0:
            self._fail(f"Expected text absent but found {count} matches: {text}")
        self._snap()

    def assert_element_count(self, selector: str, count: int):
        self._record("assert_element_count", f"{selector} == {count}")
        actual = self.page.locator(selector).count()
        if actual != count:
            self._fail(f"Expected {count} elements for {selector}, found {actual}")
        self._snap()

    # ── Evidence capture ───────────────────────────────────────────────

    def screenshot(self, label: str):
        """Take an explicitly-labeled screenshot (in addition to automatic ones)."""
        name = f"{self.scenario_name}_{self._step:02d}_{label}.png"
        path = self.screenshot_dir / name
        self.page.screenshot(path=str(path))
        log.info("[%s] Screenshot: %s", self.scenario_name, name)

    def snapshot_dom(self, label: str):
        """Capture the current interactive element list."""
        elements = self.page.evaluate(EXTRACT_ELEMENTS_JS)
        name = f"{self.scenario_name}_{self._step:02d}_{label}.json"
        path = self.screenshot_dir / name
        path.write_text(json.dumps(elements, indent=2))
        log.info("[%s] DOM snapshot: %s", self.scenario_name, name)
        return elements

    def result(self, intent_name: str) -> ReplayResult:
        """Build the final result after all steps have executed."""
        failed = any(s.error for s in self._steps)
        failure_step = next(
            (s.number for s in self._steps if s.error), None
        )
        return ReplayResult(
            intent=intent_name,
            status="fail" if failed else "done",
            steps=self._steps,
            failure_step=failure_step,
            error=self._steps[failure_step - 1].error if failure_step else None,
        )

    # ── Internals ──────────────────────────────────────────────────────

    def _record(self, action: str, detail: str):
        self._step += 1
        step = ReplayStep(number=self._step, action=action, detail=detail)
        self._steps.append(step)
        log.info(
            "[%s] Step %d: %s(%s)", self.scenario_name, self._step, action, detail
        )

    def _snap(self):
        """Auto-snapshot after every action."""
        step = self._steps[-1]
        name = f"{self.scenario_name}_{self._step:02d}_{step.action}.png"
        path = self.screenshot_dir / name
        self.page.screenshot(path=str(path))
        step.screenshot = str(path)

        elements = self.page.evaluate(EXTRACT_ELEMENTS_JS)
        step.dom_snapshot = elements

    def _settle(self):
        """Wait for async page updates: one animation frame + networkidle."""
        self.page.wait_for_timeout(50)
        try:
            self.page.wait_for_load_state("networkidle", timeout=500)
        except Exception:
            pass

    def _fail(self, message: str):
        """Mark the current step as failed and raise."""
        step = self._steps[-1]
        step.error = message
        self._snap()
        raise ReplayStepError(step)
