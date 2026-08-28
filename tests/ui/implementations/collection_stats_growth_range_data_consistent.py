"""
Hand-written implementation for collection_stats_growth_range_data_consistent.

Each range pill is a separate server-side computation over a different window,
so this asserts the windows agree with each other on the days they share --
including the carried-in position at a window's first day, which is the part
that regresses silently (a wrong opening balance changes one point, not the
shape of the chart).
"""


# Identical seed to collection_stats_growth_chart_renders: acquisitions spread
# over 120 days, price rows only every 5th day so a window start can land in a
# gap and must inherit the carried-in price.
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

# Both datasets as [date, count, value] triples, so a range mismatch names the
# exact day it diverged.
_READ_SERIES = """
(() => {
  const c = Chart.getChart('growth-chart-canvas');
  if (!c) return null;
  const n = c.data.datasets[0].data;
  const v = c.data.datasets[1].data;
  return n.map((p, i) => [p.x, Number(p.y), Number(v[i].y)]);
})()
"""


def _select_range(harness, data_range, expected_points):
    """Click a range pill and wait for the chart to actually carry its series."""
    harness.click_by_selector(
        f"#growth-range-pills .price-range-pill[data-range='{data_range}']"
    )
    harness.page.wait_for_function(
        "(n) => { const c = Chart.getChart('growth-chart-canvas');"
        "         return c && c.data.datasets[0].data.length === n; }",
        arg=expected_points,
        timeout=15_000,
    )
    return harness.page.evaluate(_READ_SERIES)


def steps(harness):
    harness.db_exec(_SEED)

    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=15_000)
    harness.wait_for_text("45 cards", timeout=15_000)

    harness.click_by_selector("#status")
    harness.wait_for_visible("#stats-modal-overlay.active", timeout=10_000)
    harness.wait_for_visible("#growth-chart-canvas", timeout=15_000)

    # Opens on 3M: 90-day window, 91 inclusive days.
    harness.page.wait_for_function(
        "() => { const c = Chart.getChart('growth-chart-canvas');"
        "        return c && c.data.datasets[0].data.length === 91; }",
        timeout=15_000,
    )
    three_month = harness.page.evaluate(_READ_SERIES)
    assert three_month is not None, "Chart.js never instantiated the growth chart"
    harness.screenshot("opened_on_3m")

    # The window opens on a carried-in position, not from scratch: the cards
    # already owned 90 days ago are counted and priced on day 0.
    assert three_month[0][1] > 1, (
        "3M window opened at count "
        f"{three_month[0][1]} — carried-in quantity was not applied"
    )
    assert three_month[0][2] > 0, (
        "3M window opened at value 0 — the price carried in from before the "
        "window start was lost"
    )

    # Widen to ALL: the line extends back to the earliest acquisition.
    all_series = _select_range(harness, 0, 121)
    assert all_series[0][1] == 1, (
        f"full history should open at the first card, got {all_series[0][1]}"
    )

    # Today is unchanged by how far back the chart looks.
    assert all_series[-1] == three_month[-1], (
        f"latest point changed with range: {three_month[-1]} vs {all_series[-1]}"
    )

    # Every day the two windows share must agree exactly — this is where a
    # wrong carried-in position or a mis-clamped day offset shows up.
    assert all_series[-91:] == three_month, (
        "3M series does not match the last 91 days of the full history; first "
        "divergence at "
        f"{next(a for a, b in zip(all_series[-91:], three_month) if a != b)}"
    )

    # Narrowing is served from the payload already held; it must still agree.
    one_month = _select_range(harness, 30, 31)
    assert all_series[-31:] == one_month, (
        "1M series does not match the last 31 days of the full history"
    )

    # Returning to a previously shown range reproduces it exactly.
    back_to_three = _select_range(harness, 90, 91)
    assert back_to_three == three_month, (
        "returning to 3M did not reproduce the series shown on open"
    )

    harness.assert_text_absent("Failed to load growth history")
    harness.screenshot("final_state")
