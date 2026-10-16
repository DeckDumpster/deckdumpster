"""Set-browse tiles at phone width: pips not NF/FOIL buttons, price over the art.

Mechanical layout invariants read off the rendered DOM (like
test_nav_reachability.py), not a Claude-graded scenario.

    uv run pytest tests/ui/test_tile_pips_and_price_overlay.py -v --instance <instance>
"""

from .budget import ROUND_TRIP_BUDGET_MS, budget_ms

# Under the art there may be exactly one row: the pip row (18px + 4px margin).
# The old layout also carried the SF/CK badge row (~22px) beneath the art.
MAX_BELOW_ART_PX = 26

_MEASURE = """() => [...document.querySelectorAll('.sheet-card')].map(t => {
  const r = e => e && e.getBoundingClientRect();
  const wrap = r(t.querySelector('.sheet-card-img-wrap'));
  const tile = r(t);
  const pips = [...t.querySelectorAll('.finish-pip')].map(r);
  const prices = [...t.querySelectorAll('.price-overlay a')].map(r);
  return {
    below: tile.height - wrap.height,
    wrap: {t: wrap.top, b: wrap.bottom, l: wrap.left, r: wrap.right},
    pipTexts: [...t.querySelectorAll('.finish-pip')].map(p => p.textContent.trim()),
    pipTops: pips.map(p => Math.round(p.top)),
    prices: prices.map(p => ({t: p.top, b: p.bottom, l: p.left, r: p.right})),
    infoLinks: t.querySelectorAll('.sheet-card-info a').length,
    buttonTexts: [...t.querySelectorAll('button')].map(b => b.textContent.trim()),
  };
})"""


def test_tiles_use_pips_and_overlay_price(browser, base_url):
    context = browser.new_context(
        viewport={"width": 390, "height": 844}, ignore_https_errors=True
    )
    try:
        page = context.new_page()
        page.goto(f"{base_url}/sets/spg", wait_until="load",
                  timeout=budget_ms(ROUND_TRIP_BUDGET_MS))
        page.wait_for_selector(".sheet-card .finish-pip",
                               timeout=budget_ms(ROUND_TRIP_BUDGET_MS))
        tiles = page.evaluate(_MEASURE)
    finally:
        context.close()

    assert tiles
    for t in tiles:
        assert not {"NF", "FOIL", "Foil"} & set(t["buttonTexts"]), t["buttonTexts"]
        assert not any(x in ("NF", "FOIL") or x.startswith("NF ") for x in t["buttonTexts"])
        assert len(set(t["pipTops"])) == 1, f"pip row wraps: {t['pipTops']}"
        assert t["infoLinks"] == 0, "price links still sit in a row below the art"
        assert t["below"] <= MAX_BELOW_ART_PX, (
            f"{t['below']:.0f}px under the art; only the pip row belongs there"
        )
        for p in t["prices"]:
            w = t["wrap"]
            assert w["l"] <= p["l"] and p["r"] <= w["r"] and w["t"] <= p["t"] and p["b"] <= w["b"], (
                f"price badge {p} outside the card image box {w}"
            )
