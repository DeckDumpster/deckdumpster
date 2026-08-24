"""
Hand-written implementation for sets_binder_modal_foil_only_printing.

Opens a foil-only printing and its ordinary sibling, and checks the modal offers
one finish row for the first and two for the second, with the foil-kind badge on
the first alone.
"""

NEONINK = "b3ce1be9-8ee7-4956-a895-ca22759ccf65"   # Mana Crypt 17a, foil only
PLAIN = "ecb293d5-b13b-400f-ac7b-162a1e127ec7"     # Mana Crypt 17, nonfoil + foil


def _open(harness, printing_id):
    harness.click_by_selector(f'.sheet-card[data-printing-id="{printing_id}"] .sheet-card-img-wrap')
    harness.wait_for_visible(".card-modal-overlay.active", timeout=3_000)
    harness.wait_for_visible("#binder-condition", timeout=3_000)


def _finishes(harness):
    return harness.page.eval_on_selector_all(
        ".binder-count", "els => els.map(e => e.dataset.finish)")


def steps(harness):
    # start_page: /sets/spg?q=Mana%20Crypt — auto-navigated by the test runner.

    harness.wait_for_text("7 printings", timeout=5_000)

    # The foil-only printing: one pocket, and it is a foil one.
    _open(harness, NEONINK)
    assert _finishes(harness) == ["foil"], (
        f"Foil-only printing offered {_finishes(harness)}")
    harness.assert_element_count(".binder-finish", 1)

    badges = harness.page.eval_on_selector_all(
        ".card-modal-details .badge.foil-kind", "els => els.map(e => e.textContent)")
    assert badges == ["NeonInk"], f"Foil-kind badges are {badges}"
    harness.screenshot("neonink_printing")

    harness.click_by_selector(".card-modal-close")
    harness.wait_for_hidden(".card-modal-overlay.active", timeout=3_000)

    # Its ordinary sibling: both pockets, and no foil-kind badge to confuse it
    # with the one above.
    _open(harness, PLAIN)
    assert _finishes(harness) == ["nonfoil", "foil"], (
        f"Plain printing offered {_finishes(harness)}")
    harness.assert_element_count(".binder-finish", 2)
    harness.assert_element_count(".card-modal-details .badge.foil-kind", 0)

    harness.screenshot("final_state")
