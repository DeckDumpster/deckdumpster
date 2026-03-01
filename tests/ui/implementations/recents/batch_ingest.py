"""
Hand-written implementation for batch_ingest.

The fixture has 2 DONE cards (Mox Emerald, Armed Response) that are
already resolved. Clicking "Batch Ingest" ingests them into the
collection. Then navigate to /collection and search to verify.
"""


def steps(harness):
    # The default 2h pill shows all 5 images, 2 already resolved (green).
    # Click "Batch Ingest" — it's visible because resolved cards exist.
    harness.click_by_text("Batch Ingest")
    # Verify success message appeared.
    harness.wait_for_text("photos inserted")
    # Navigate to collection to verify the cards were added.
    harness.navigate("/collection")
    harness.fill_by_placeholder("Search cards...", "Armed Response")
    harness.screenshot("final_state")
