"""
Hand-written implementation for collection_stats_growth_chart_renders.

Seeds acquisition history and price history via podman exec, then opens the
result-stats modal and verifies the "Growth over time" chart actually renders
instead of falling back to the empty-state placeholder.
"""

import subprocess

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


def _find_container(base_url):
    """Find the container serving the given base_url by matching its port."""
    port = base_url.rstrip("/").rsplit(":", 1)[-1]
    result = subprocess.run(
        ["podman", "ps", "--format", "{{.Names}}"], capture_output=True, text=True
    )
    for name in result.stdout.strip().split("\n"):
        if not name:
            continue
        port_result = subprocess.run(
            ["podman", "port", name, "8081/tcp"], capture_output=True, text=True
        )
        if port in port_result.stdout:
            return name
    raise AssertionError(f"no container found serving {base_url}")


def steps(harness):
    # The --test fixture has no acquisition spread and almost no prices, so
    # the chart would otherwise be a single point at $0.
    container = _find_container(harness.base_url)
    subprocess.run(
        ["podman", "exec", container, "python3", "-c", _SEED],
        capture_output=True, text=True, check=True,
    )

    # Reload so the collection list is served from the seeded DB.
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=15_000)
    harness.wait_for_text("45 cards", timeout=15_000)

    # Open the result-stats modal from the inline result count.
    harness.click_by_selector("#status")
    harness.wait_for_visible("#stats-modal-overlay.active", timeout=10_000)

    # The growth section is the first section in the modal.
    harness.assert_text_present("Growth over time")

    # The chart is fetched lazily when the modal opens, so wait for the canvas.
    harness.wait_for_visible("#growth-chart-canvas", timeout=15_000)
    harness.assert_visible("#growth-range-pills")

    # Neither the empty state nor the fetch-failure state may be showing.
    harness.assert_text_absent("No acquisition history for the current filter")
    harness.assert_text_absent("Failed to load growth history")

    # The canvas element exists in the markup even if Chart.js never drew, so
    # assert against the live Chart instance. Datasets are arrays of {x, y}
    # points (there is no labels array): dataset 0 is the card count, dataset 1
    # is the value series.
    chart = harness.page.evaluate(
        "(() => {"
        "  const c = Chart.getChart('growth-chart-canvas');"
        "  if (!c) return null;"
        "  const ys = i => c.data.datasets[i].data.map(p => Number(p.y));"
        "  return {datasets: c.data.datasets.length,"
        "          points: c.data.datasets[0].data.length,"
        "          firstCount: ys(0)[0], lastCount: ys(0).slice(-1)[0],"
        "          maxValue: Math.max(...ys(1))};"
        "})()"
    )
    assert chart is not None, "Chart.js never instantiated the growth chart"
    assert chart["datasets"] == 2, f"expected count + value datasets, got {chart['datasets']}"
    assert chart["points"] > 100, f"expected the full ~121-day series, got {chart['points']}"
    # The collection grows over the window, and the value series is not flat zero.
    assert chart["lastCount"] > chart["firstCount"], (
        f"count series did not grow: {chart['firstCount']} -> {chart['lastCount']}"
    )
    assert chart["maxValue"] > 0, "value series is flat zero — prices did not resolve"

    harness.screenshot("final_state")
