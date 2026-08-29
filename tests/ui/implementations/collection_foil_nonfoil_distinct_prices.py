"""
Hand-written implementation for collection_foil_nonfoil_distinct_prices.

Seeds distinct foil vs non-foil prices for fdn/132 (Scrawling Crawler, owned in
both finishes) into the shared reference DB, searches for the card in the
collection, and verifies the foil row shows the foil price while the non-foil
row shows the non-foil price.

Regression guard: before the fix, price_type was derived from the printing's
available finishes (p.finishes) instead of the copy's actual finish (c.finish),
so both rows showed the non-foil price and the foil "$99.00" never appeared.
"""


def steps(harness):
    # Seed distinct foil/non-foil prices into the SHARED reference DB.
    # latest_prices is a shared table (/data/shared.sqlite), not collection.sqlite.
    seed_script = (
        "import sqlite3\n"
        "s = sqlite3.connect('/data/shared.sqlite')\n"
        "s.execute(\"DELETE FROM latest_prices WHERE set_code='fdn' AND collector_number='132'\")\n"
        "for src, ptype, price in [\n"
        "    ('tcgplayer','normal','3.00'), ('tcgplayer','foil','99.00'),\n"
        "    ('cardkingdom','normal','3.30'), ('cardkingdom','foil','110.00')]:\n"
        "    s.execute(\n"
        "        'INSERT INTO latest_prices (set_code, collector_number, source, price_type, price, observed_at) '\n"
        "        \"VALUES (?,?,?,?,?, '2026-06-01T00:00:00Z')\", ('fdn','132',src,ptype,price))\n"
        "s.commit(); s.close()\n"
    )
    harness.db_exec(seed_script)

    # start_page: /collection — auto-navigated by the test runner.
    # Search for the card owned in both finishes.
    harness.fill_by_placeholder("Search (e.g. t:creature c:r mv>=3)", "Scrawling Crawler")
    # Default table view groups by finish: a foil row and a non-foil row.
    harness.wait_for_visible("tr[data-idx]", timeout=15_000)

    # Regression guard: the foil price must appear. Before the fix both rows
    # showed the non-foil price ($3.00) and $99.00 never rendered. Waiting on
    # the foil price also gates on the debounced filtered result settling.
    harness.wait_for_text("$99.00", timeout=10_000)
    harness.assert_text_present("$99.00")
    # The non-foil row still shows the non-foil price.
    harness.assert_text_present("$3.00")
    # Exactly two rows (foil + non-foil grouping).
    harness.assert_element_count("tr[data-idx]", 2)
    harness.screenshot("final_state")
