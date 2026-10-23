"""Tenant B opens every page and sees none of tenant A (sp-ntlyxy).

The API tier (`tests/integration/test_two_tenants.py`) proves the JSON; this proves
what a person reads. A browser signs in through the Access header as `bobby`, whose
file is empty, and visits every routed page against the production container shape
(`tests/two_tenant_stack.py`): none of `alice`'s data may render -- not a card, not a
deck, not the "45 cards, $10.46" header on the collection page, not an "N owned" on
the set index. Each page is also opened as alice, who must see her own data, so a
page that rendered nothing for anyone cannot pass.

Default-deny like `test_nav_reachability.py`: the page list is `PAGE_ROUTES`, so a new
page is swept the moment it is routed. Parametrized routes need a sample URL here.

Usage:
    uv run pytest tests/ui/test_two_tenant_pages.py -v --instance <instance>
"""

import re

import pytest

from mtg_collector.cli.page_routes import PAGE_ROUTES

from .budget import INTERACTION_BUDGET_MS, ROUND_TRIP_BUDGET_MS, budget_ms

PAGES = tuple(r.path for r in PAGE_ROUTES)


def _urls(ids):
    return {
        "/deck-builder/": f"/deck-builder/{ids['deck']}",
        "/decks/": f"/decks/{ids['deck']}",
        "/deck-groups/": f"/deck-groups/{ids['group']}",
        "/sets/": "/sets/dsk",
        "/card/": "/card/dsk/1",
        "/batches/": f"/batches/{ids['batch']}",
        "/orders/": f"/orders/{ids['order']}",
    }


@pytest.fixture(scope="module")
def alice_data(two_tenants):
    """What alice owns, read from the API: the strings and figures that must never reach bobby."""
    a = two_tenants.alice

    def ok(path):
        status, body = a.get(path)
        assert status == 200, f"{path} -> {status}"
        return body

    status, deck = a.json("POST", "/api/decks", {"name": "ntly-secret-deck", "format": "commander"})
    assert status == 201, deck
    status, group = a.json("POST", "/api/deck-groups", {"name": "ntly-secret-group"})
    assert status == 201, group
    status, binder = a.json("POST", "/api/binders", {"name": "ntly-secret-binder"})
    assert status == 201, binder

    names = set()
    for path, keys in (
        ("/api/decks", ("name", "description")),
        ("/api/deck-groups", ("name",)),
        ("/api/binders", ("name",)),
        ("/api/orders", ("order_number",)),
        ("/api/batches", ("name",)),
        ("/api/views", ("name",)),
        ("/api/ingest2/images", ("filename",)),
    ):
        for row in ok(path):
            names.update(str(row[k]) for k in keys if row.get(k))
    page = ok("/api/collection?limit=1")
    assert page["total_qty"] > 0 and page["total_value"] > 0, "alice has no collection to hide"
    return {
        "names": names,
        "header": f"{page['total_qty']:,} cards",
        "value": f"${page['total_value']:,.2f}",
        "ids": {
            "deck": ok("/api/decks")[0]["id"],
            "group": group["id"],
            "batch": ok("/api/batches")[0]["id"],
            "order": ok("/api/orders")[0]["id"],
        },
        "cards": [r["name"] for r in ok("/api/collection?limit=20")["rows"]],
    }


def _render(browser, base, tenant, url):
    """The text a person reads on `url` once the page's own API calls have been answered.

    Not `networkidle`: /orders/:id and /batches/:id for a record the tenant does not
    have never report idle (their requests are answered and never "finish"), and a
    page that has been answered is what is being read.
    """
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 900},
        ignore_https_errors=True,
        extra_http_headers=tenant.headers,
    )
    try:
        page = ctx.new_page()
        asked, answered = [], []
        page.on("request", lambda r: asked.append(r.url) if "/api/" in r.url else None)
        page.on("response", lambda r: answered.append(r.url) if "/api/" in r.url else None)
        response = page.goto(base + url, wait_until="load", timeout=budget_ms(ROUND_TRIP_BUDGET_MS))
        assert response.status == 200, f"{tenant.email} {url} -> {response.status}"
        step = 50
        for _ in range(budget_ms(ROUND_TRIP_BUDGET_MS) // step):
            if len(answered) >= len(asked):
                break
            page.wait_for_timeout(step)
        else:
            raise AssertionError(f"{url}: {len(asked) - len(answered)} API calls unanswered")
        page.wait_for_timeout(budget_ms(INTERACTION_BUDGET_MS))
        return " ".join(page.inner_text("body").split())
    finally:
        ctx.close()


@pytest.mark.parametrize("route", PAGES)
def test_b_sees_no_trace_of_a_on_any_page(route, browser, two_tenants, alice_data):
    urls = _urls(alice_data["ids"])
    url = urls.get(route, route)
    base = two_tenants.base

    theirs = _render(browser, base, two_tenants.bobby, url)
    leaked = [n for n in alice_data["names"] | {"ntly-secret-deck", "ntly-secret-binder"} if n in theirs]
    assert not leaked, f"bobby's {url} renders alice's data: {leaked}"
    assert alice_data["header"] not in theirs, f"bobby's {url} shows alice's card count"
    assert alice_data["value"] not in theirs, f"bobby's {url} shows alice's collection value"
    assert not re.search(r"\b[1-9][\d,]* owned\b", theirs), f"bobby's {url} reports owned sets: {theirs[:300]}"


def test_the_collection_page_is_alices_for_alice_and_empty_for_bobby(browser, two_tenants, alice_data):
    base = two_tenants.base
    mine = _render(browser, base, two_tenants.alice, "/collection")
    assert alice_data["header"] in mine and alice_data["value"] in mine, (
        f"control arm: alice's collection header is not '{alice_data['header']}, {alice_data['value']}': {mine[:200]}"
    )
    theirs = _render(browser, base, two_tenants.bobby, "/collection")
    assert [c for c in alice_data["cards"] if c in theirs] == [], "bobby's collection lists alice's cards"
    assert "0 results" in theirs or "No cards found" in theirs, theirs[:300]


@pytest.mark.parametrize("route,marker", [
    ("/decks", "ntly-secret-deck"),
    ("/binders", "ntly-secret-binder"),
    ("/orders", "DEMO-TCG-001"),
    ("/batches", "New cards from LGS"),
    ("/sealed", "7 entries"),
    ("/sets", "owned"),
])
def test_control_arm_alice_sees_her_own_data(route, marker, browser, two_tenants, alice_data):
    text = _render(browser, two_tenants.base, two_tenants.alice, route)
    assert marker in text, f"alice's {route} lacks '{marker}': {text[:300]}"
