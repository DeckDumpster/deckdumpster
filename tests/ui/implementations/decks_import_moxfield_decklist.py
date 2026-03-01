"""
Hand-written implementation for decks_import_moxfield_decklist.

Imports a text decklist "1 Scrawling Crawler (FDN) 132" through the
CSV Import page and verifies the card resolves successfully.
"""


def steps(harness):
    # Select "Deck List (text)" format.
    harness.select_by_label("#format-select", "Deck List (text)")
    # Paste the decklist into the textarea.
    harness.fill_by_selector("#csv-text", "1 Scrawling Crawler (FDN) 132")
    # Click "Parse & Resolve".
    harness.click_by_selector("#parse-btn")
    # Wait for resolution results.
    harness.wait_for_text("Scrawling Crawler")
    harness.screenshot("final_state")
