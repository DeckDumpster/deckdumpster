"""
Brimstone Mage is inserted by --demo as READY_FOR_OCR. The server (with
MTGC_FAKE_AGENT=1) processes it on startup: OCR runs locally, fake agent
returns two candidates. _resolve_candidates should match the ROE printing
despite the unicode artist name ("Volkan Bağa" in DB vs "Volkan Baga"
from agent). With only 1 candidate in the fixture DB, auto-disambiguation
selects it and the card goes directly to DONE.

All 3 demo ingest images should be done — none stuck at needs_disambiguation.

Requires MTGC_FAKE_AGENT=1 and ROE cached in the fixture DB.
"""


def steps(harness):
    # Brimstone Mage was inserted as READY_FOR_OCR by --demo.
    # Server processes it on startup. Wait for cards to appear.
    harness.navigate("/recent")
    harness.wait_for_visible(".img-card", timeout=15_000)

    # After the unicode artist fix, _resolve_candidates finds the ROE
    # printing. With 1 candidate, auto-disambiguation selects it.
    # All 3 demo cards should be done — none should need disambiguation.
    # Before the fix, Brimstone Mage would be needs_disambiguation.
    harness.assert_element_count(".img-card.needs_disambiguation", 0)

    harness.screenshot("final_state")
