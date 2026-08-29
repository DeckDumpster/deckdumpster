"""
Hand-written implementation for collection_stats_growth_short_history_opens_on_all.

Seeds a collection whose entire history (~20 days) is shorter than the chart's
default 3-month range, then verifies the chart opens on ALL rather than leaving
a greyed-out pill selected, and still renders the real series.
"""


# As collection_stats_growth_chart_renders, but compressed to 20 days with
# prices every 2nd day.
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
    d = today - dt.timedelta(days=20 - (n * 20 // max(len(ids), 1)))
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
    for k in range(0, 21, 2):
        d = (today - dt.timedelta(days=20 - k)).isoformat()
        grow = 1.0 + k / 40.0
        for src, pt, mult in (('tcgplayer', 'normal', 1.0),
                              ('cardkingdom', 'normal', 0.92),
                              ('tcgplayer', 'foil', 2.4),
                              ('cardkingdom', 'foil', 2.2)):
            rows.append((sc, cn, src, pt, round(base * grow * mult, 2), d))
sh.executemany("INSERT OR REPLACE INTO prices "
               "(set_code,collector_number,source,price_type,price,observed_at) "
               "VALUES (?,?,?,?,?,?)", rows)
sh.commit()
"""


def steps(harness):
    # 20 days of history: shorter than every finite range pill.
    harness.db_exec(_SEED)

    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=15_000)
    harness.wait_for_text("45 cards", timeout=15_000)

    harness.click_by_selector("#status")
    harness.wait_for_visible("#stats-modal-overlay.active", timeout=10_000)
    harness.wait_for_visible("#growth-chart-canvas", timeout=15_000)

    # Every finite range exceeds the seeded span, so only ALL is selectable.
    harness.assert_element_count("#growth-range-pills .price-range-pill.disabled", 4)
    harness.assert_element_count(
        "#growth-range-pills .price-range-pill:not(.disabled)", 1
    )

    # The selected pill is ALL, not the greyed-out 3M default.
    harness.assert_visible("#growth-range-pills .price-range-pill.active[data-range='0']")
    harness.assert_element_count("#growth-range-pills .price-range-pill.active", 1)

    # A disabled pill is never the selected one.
    harness.assert_element_count(
        "#growth-range-pills .price-range-pill.active.disabled", 0
    )
    harness.screenshot("opens_on_all")

    # The real 21-day series is drawn, not the empty-state placeholder.
    harness.assert_text_absent("No acquisition history for the current filter")
    harness.assert_text_absent("Failed to load growth history")
    chart = harness.page.evaluate(
        "(() => {"
        "  const c = Chart.getChart('growth-chart-canvas');"
        "  if (!c) return null;"
        "  const ys = i => c.data.datasets[i].data.map(p => Number(p.y));"
        "  return {points: c.data.datasets[0].data.length,"
        "          lastCount: ys(0).slice(-1)[0],"
        "          maxValue: Math.max(...ys(1))};"
        "})()"
    )
    assert chart is not None, "Chart.js never instantiated the growth chart"
    assert chart["points"] == 21, (
        f"expected the full 21-day history, got {chart['points']}"
    )
    assert chart["lastCount"] == 45, (
        f"expected all 45 seeded cards by today, got {chart['lastCount']}"
    )
    assert chart["maxValue"] > 0, "value series is flat zero — prices did not resolve"

    harness.screenshot("final_state")
