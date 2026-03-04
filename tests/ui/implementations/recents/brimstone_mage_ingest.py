"""
Brimstone Mage is inserted by --demo as READY_FOR_OCR. The server (with
MTGC_FAKE_AGENT=1) processes it on startup: OCR runs locally, fake agent
returns two candidates, but _resolve_candidates fails on unicode artist
mismatch ("Volkan Baga" vs "Volkan Bağa") — card lands as
needs_disambiguation with empty scryfall_matches.

Open the accordion, search for the card, select a candidate from search
results, and verify the candidate gets a green "selected" border.

Requires MTGC_FAKE_AGENT=1 and ROE cached in the fixture DB.
"""


def steps(harness):
    # Brimstone Mage was inserted as READY_FOR_OCR by --demo.
    # Server processes it on startup. Wait for the card grid to load.
    harness.navigate("/recent")
    harness.wait_for_visible(".img-card.needs_disambiguation", timeout=15_000)

    # Click the needs_disambiguation card to open accordion.
    harness.click_by_selector(".img-card.needs_disambiguation")
    harness.assert_visible("#accordion-panel.open")

    # Search for "Brimstone Mage" in the accordion search box.
    harness.fill_by_selector('[id^="acc-search-input-"]', "Brimstone Mage")
    harness.press_key("Enter", selector='[id^="acc-search-input-"]')

    # Wait for search results, select first candidate.
    harness.wait_for_visible(".acc-candidates .acc-candidate", timeout=10_000)
    harness.click_by_selector(".acc-candidates .acc-candidate:first-child")

    # Candidate should get the "selected" border after being clicked.
    harness.wait_for_visible(".acc-candidates .acc-candidate.selected", timeout=5_000)
    harness.screenshot("final_state")
