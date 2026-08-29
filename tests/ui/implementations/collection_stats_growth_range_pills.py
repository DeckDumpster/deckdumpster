"""
Hand-written implementation for collection_stats_growth_range_pills.

Seeds ~120 days of history so the 1M/3M ranges are covered but 6M/1Y are not,
then verifies the pills grey out accordingly, that 3M is selected on open, and
that clicking an enabled pill moves the active selection while clicking a
greyed-out one does nothing.
"""


# Spread acquired_at over the last 120 days and write price rows every 5th day
# (deliberate gaps, so the server-side forward-fill is exercised) for both
# sources in both price_types, plus buylist rows the endpoint must ignore.
#
# Prices go into /data/shared.sqlite, NOT /data/collection.sqlite: the test
# container sets MTGC_SHARED_DB and attach_shared() creates temp views that
# shadow the main-schema tables, so rows written to collection.sqlite's
# `prices` table are invisible to the server.
_SEED = """
import sqlite3, datetime as dt
col = sqlite3.connect('/data/collection.sqlite')
sh = sqlite3.connect('/data/shared.sqlite')
today = dt.date.today()
ids = [r[0] for r in col.execute("SELECT id FROM collection ORDER BY id")]
for n, cid in enumerate(ids):
    d = today - dt.timedelta(days=120 - (n * 120 // max(len(ids), 1)))
    col.execute("UPDATE collection SET acquired_at=? WHERE id=?",
                (d.isoformat() + "T12:00:00.000Z", cid))
col.commit()
pids = [r[0] for r in col.execute("SELECT DISTINCT printing_id FROM collection")]
q = ",".join("?" * len(pids))
pairs = [tuple(r) for r in sh.execute(
    "SELECT DISTINCT set_code, collector_number FROM printings "
    "WHERE printing_id IN (%s)" % q, pids)]
rows = []
for i, (sc, cn) in enumerate(pairs):
    base = 2.0 + (i % 20)
    for k in range(0, 121, 5):
        d = (today - dt.timedelta(days=120 - k)).isoformat()
        grow = 1.0 + k / 240.0
        for src, pt, mult in (('tcgplayer', 'normal', 1.0),
                              ('cardkingdom', 'normal', 0.92),
                              ('tcgplayer', 'foil', 2.4),
                              ('cardkingdom', 'foil', 2.2),
                              ('cardkingdom', 'buylist_normal', 0.4)):
            rows.append((sc, cn, src, pt, round(base * grow * mult, 2), d))
sh.executemany("INSERT OR REPLACE INTO prices "
               "(set_code,collector_number,source,price_type,price,observed_at) "
               "VALUES (?,?,?,?,?,?)", rows)
sh.commit()
"""


def steps(harness):
    # 120 days of history: long enough for 1M (30) and 3M (90), short enough
    # that 6M (180) and 1Y (365) must be disabled.
    harness.db_exec(_SEED)

    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=15_000)
    harness.wait_for_text("45 cards", timeout=15_000)

    harness.click_by_selector("#status")
    harness.wait_for_visible("#stats-modal-overlay.active", timeout=10_000)
    harness.wait_for_visible("#growth-chart-canvas", timeout=15_000)

    # All five pills exist; 3M is the default selection.
    harness.assert_element_count("#growth-range-pills .price-range-pill", 5)
    harness.assert_visible("#growth-range-pills .price-range-pill.active[data-range='90']")
    harness.assert_element_count("#growth-range-pills .price-range-pill.active", 1)

    # 6M and 1Y exceed the seeded span, so exactly those two are disabled.
    harness.assert_element_count("#growth-range-pills .price-range-pill.disabled", 2)
    harness.assert_visible("#growth-range-pills .price-range-pill.disabled[data-range='180']")
    harness.assert_visible("#growth-range-pills .price-range-pill.disabled[data-range='365']")

    # 1M, 3M and ALL remain selectable.
    harness.assert_element_count("#growth-range-pills .price-range-pill:not(.disabled)", 3)
    harness.screenshot("pills_initial")

    # Widening to ALL moves the active marker and redraws over the full span.
    # The pill class flips before the fetch resolves, so wait on the chart data.
    harness.click_by_selector("#growth-range-pills .price-range-pill[data-range='0']")
    harness.page.wait_for_function(
        "() => { const c = Chart.getChart('growth-chart-canvas');"
        "        return c && c.data.datasets[0].data.length === 121; }",
        timeout=15_000,
    )
    harness.assert_visible("#growth-range-pills .price-range-pill.active[data-range='0']")
    harness.assert_element_count("#growth-range-pills .price-range-pill.active", 1)

    # Narrowing to 1M is served from the payload already held.
    harness.click_by_selector("#growth-range-pills .price-range-pill[data-range='30']")
    harness.page.wait_for_function(
        "() => { const c = Chart.getChart('growth-chart-canvas');"
        "        return c && c.data.datasets[0].data.length === 31; }",
        timeout=15_000,
    )
    harness.assert_visible("#growth-range-pills .price-range-pill.active[data-range='30']")

    # A greyed-out range cannot be selected at all: .disabled sets
    # pointer-events: none, so the click never reaches 1Y and 1M stays active.
    # (Asserted via computed style rather than by clicking — Playwright
    # correctly refuses to click an element that cannot receive pointer events.)
    pointer_events = harness.page.eval_on_selector(
        "#growth-range-pills .price-range-pill[data-range='365']",
        "el => getComputedStyle(el).pointerEvents",
    )
    assert pointer_events == "none", (
        f"disabled 1Y pill is still clickable (pointer-events: {pointer_events})"
    )
    harness.assert_visible("#growth-range-pills .price-range-pill.active[data-range='30']")
    harness.assert_element_count("#growth-range-pills .price-range-pill.active", 1)

    # The chart is still rendered after the updates.
    harness.assert_visible("#growth-chart-canvas")

    harness.screenshot("final_state")
