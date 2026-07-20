"""Regression tests for the replay harness's text assertions (efj-mtgc-h9z).

Both assertions previously sampled ``page.get_by_text(text).count()`` with no
waiting.  On a page that renders from an async fetch that races the render:

* ``assert_text_present`` fails even though the text arrives moments later.
* ``assert_text_absent`` passes *vacuously* — nothing has rendered, so the
  count is trivially 0 and the assertion proves nothing.

These use a fake page that models an async render, so they are deterministic
rather than load-dependent.
"""

import pytest

from tests.ui.replay import ReplayHarness, ReplayStepError


class _FakeLocator:
    def __init__(self, page, text):
        self._page, self._text = page, text

    @property
    def first(self):
        return self

    def count(self):
        return 1 if self._text in self._page.rendered else 0

    def wait_for(self, state=None, timeout=None):
        """Model Playwright auto-waiting: the pending render lands."""
        self._page.flush()
        if self._text not in self._page.rendered:
            raise TimeoutError(f"waiting for {self._text}")


class _FakePage:
    """A page whose content only appears once something waits for it."""

    def __init__(self, pending=()):
        self.rendered, self.pending = set(), set(pending)
        self.settled = False

    def flush(self):
        self.rendered |= self.pending
        self.pending = set()

    def get_by_text(self, text, exact=False):
        return _FakeLocator(self, text)

    # Harness plumbing the assertions touch.
    def wait_for_timeout(self, ms):
        self.settled = True
        self.flush()

    def wait_for_load_state(self, state, timeout=None):
        pass

    def screenshot(self, **kw):
        return b""

    def evaluate(self, js):
        return []


def _harness(page, tmp_path):
    return ReplayHarness(page, "https://x", tmp_path, "fake_scenario")


def test_present_waits_for_async_render(tmp_path):
    """Text arriving after the assertion starts must still pass."""
    page = _FakePage(pending={"$3.50"})
    assert page.get_by_text("$3.50").count() == 0, "precondition: not yet rendered"

    _harness(page, tmp_path).assert_text_present("$3.50")


def test_present_still_fails_when_text_never_arrives(tmp_path):
    """Waiting must not paper over genuinely missing text."""
    page = _FakePage()
    with pytest.raises(ReplayStepError):
        _harness(page, tmp_path).assert_text_present("$3.50")


def test_absent_is_not_vacuous_on_unrendered_page(tmp_path):
    """Text pending render must be caught, not passed over."""
    page = _FakePage(pending={"$21.00"})
    assert page.get_by_text("$21.00").count() == 0, "precondition: not yet rendered"

    with pytest.raises(ReplayStepError):
        _harness(page, tmp_path).assert_text_absent("$21.00")


def test_absent_passes_for_genuinely_missing_text(tmp_path):
    page = _FakePage(pending={"something else"})
    _harness(page, tmp_path).assert_text_absent("$21.00")
    assert page.settled, "absent assertion must settle the page before counting"
