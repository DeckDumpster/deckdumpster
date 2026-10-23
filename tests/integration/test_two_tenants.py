"""Two tenants through the production container path (sp-ntlyxy).

`tests/test_isolation_gate.py` drives one router family in-process. Two defects
reached multi-tenant prod past it: a listener that bound the container's own
loopback (only a published port can see that) and a native collection router that
served every tenant the server's legacy file (only a family other than binders can
see that). So this runs the instance's image the way the Quadlet does, with
alice's demo data and an empty bobby, and asks every API family the same two
questions through the published port: alice sees all of hers, bobby sees none.

Every "bobby sees none" has its control arm in the same test -- alice's answer to
the same request is non-empty -- so a stack that served nobody anything cannot
pass. The stack is `tests/two_tenant_stack.py`.

    uv run pytest tests/integration/test_two_tenants.py -v --instance <instance>
"""

import json

import pytest

from mtg_collector.cli.page_routes import PAGE_ROUTES

pytestmark = pytest.mark.usefixtures("two_tenants")


@pytest.fixture(scope="module")
def alice(two_tenants):
    return two_tenants.alice


@pytest.fixture(scope="module")
def bobby(two_tenants):
    return two_tenants.bobby


def _ok(tenant, path):
    status, body = tenant.get(path)
    assert status == 200, f"{tenant.email} GET {path} -> {status} {body}"
    return body


def _first_id(alice, path):
    rows = _ok(alice, path)
    assert rows, f"alice has nothing at {path}: the stack was not seeded"
    return rows[0]["id"]


# --- list families: alice has rows, bobby has none ------------------------------

def _rows(body):
    return len(body["rows"])


def _sum_values(body):
    return sum(body.values())


def _growth_points(body):
    return sum(body["counts"])


def _sealed_entries(body):
    return body["total_entries"]


LIST_FAMILIES = {
    "collection": ("/api/collection?limit=50", _rows),
    "collection-total": ("/api/collection?limit=1", lambda b: b["total"] + b["total_qty"]),
    "search-alias": ("/api/search?q=&limit=50", _rows),
    "growth": ("/api/collection/growth", _growth_points),
    "decks": ("/api/decks", len),
    "deck-groups": ("/api/deck-groups", len),
    "binders": ("/api/binders", len),
    "sealed": ("/api/sealed/collection", len),
    "sealed-stats": ("/api/sealed/collection/stats", _sealed_entries),
    "wishlist": ("/api/wishlist", len),
    "orders": ("/api/orders", len),
    "batches": ("/api/batches", len),
    "corner-batches": ("/api/corner-batches", len),
    "views": ("/api/views", len),
    "ingest-images": ("/api/ingest2/images", len),
    "ingest-recent": ("/api/ingest2/recent", len),
    "ingest-counts": ("/api/ingest2/counts", _sum_values),
}


@pytest.mark.parametrize("family", sorted(LIST_FAMILIES))
def test_a_sees_all_b_sees_none(family, alice, bobby):
    path, count = LIST_FAMILIES[family]
    mine = count(_ok(alice, path))
    assert mine > 0, f"control arm: alice sees nothing at {path}"
    assert count(_ok(bobby, path)) == 0, f"bobby sees alice's data at {path}"


def test_collection_totals_are_alices_alone(alice, bobby):
    a, b = _ok(alice, "/api/collection?limit=1"), _ok(bobby, "/api/collection?limit=1")
    assert (a["total"], a["total_qty"]) == (43, 45)
    assert a["total_value"] > 0
    assert (b["total"], b["total_qty"], b["total_value"], b["rows"]) == (0, 0, 0, [])


# --- by-id families: alice's id is a 404 for bobby -----------------------------

@pytest.fixture(scope="module", autouse=True)
def alice_group(alice):
    """Alice's demo data holds no deck group; the group families need one to see."""
    status, group = alice.json("POST", "/api/deck-groups", {"name": "ntly-secret-group"})
    assert status == 201, group
    return group


@pytest.fixture(scope="module")
def ids(alice, alice_group):
    return {
        "group": alice_group["id"],
        "deck": _first_id(alice, "/api/decks"),
        "binder": _first_id(alice, "/api/binders"),
        "order": _first_id(alice, "/api/orders"),
        "batch": _first_id(alice, "/api/batches"),
        "view": _first_id(alice, "/api/views"),
        "copy": _ok(alice, "/api/collection/copies?printing_id="
                    + _ok(alice, "/api/collection?limit=1")["rows"][0]["printing_id"])[0]["id"],
    }


BY_ID = {
    "deck": "/api/decks/{deck}",
    "deck-group": "/api/deck-groups/{group}",
    "deck-completeness": "/api/decks/{deck}/completeness",
    "deck-builder": "/api/deck-builder/{deck}",
    "binder": "/api/binders/{binder}",
    "order": "/api/orders/{order}",
    "batch-cards": "/api/batches/{batch}/cards",
    "view": "/api/views/{view}",
}

CHILD_LISTS = {
    "deck-cards": "/api/decks/{deck}/cards",
    "binder-cards": "/api/binders/{binder}/cards",
    "order-cards": "/api/orders/{order}/cards",
}


@pytest.mark.parametrize("name", sorted(BY_ID))
def test_a_record_by_id_is_a_404_for_b(name, alice, bobby, ids):
    path = BY_ID[name].format(**ids)
    assert alice.get(path)[0] == 200, f"control arm: alice cannot read {path}"
    status, body = bobby.get(path)
    assert status == 404, f"bobby read alice's record at {path}: {status} {str(body)[:200]}"


@pytest.mark.parametrize("name", sorted(CHILD_LISTS))
def test_a_child_list_is_empty_for_b(name, alice, bobby, ids):
    path = CHILD_LISTS[name].format(**ids)
    assert _ok(alice, path), f"control arm: alice's {path} is empty"
    assert _ok(bobby, path) == []


def test_collection_copies_and_history_are_alices_alone(alice, bobby, ids):
    printing = _ok(alice, "/api/collection?limit=1")["rows"][0]["printing_id"]
    path = f"/api/collection/copies?printing_id={printing}"
    assert _ok(alice, path), "control arm: alice has no copy of her own first row"
    assert _ok(bobby, path) == []
    history = f"/api/collection/{ids['copy']}/history"
    assert any(_ok(alice, history).values()), "control arm: alice's copy has no history"
    status, body = bobby.get(history)
    assert status == 404 or not any(body.values()), f"bobby read alice's history: {str(body)[:200]}"


def test_set_browse_owns_nothing_for_b(alice, bobby):
    set_code = _ok(alice, "/api/collection?limit=1")["rows"][0]["set_code"]
    path = f"/api/set-browse/{set_code}?limit=500"
    assert sum(r["qty"] for r in _ok(alice, path)["rows"]) > 0, "control arm"
    assert sum(r["qty"] for r in _ok(bobby, path)["rows"]) == 0


# --- no byte of alice's own data in bobby's answers ---------------------------

def _alice_markers(alice):
    """Strings only alice's file holds: names she gave things, not catalogue rows."""
    marks = set()
    for path, keys in (
        ("/api/decks", ("name", "description")),
        ("/api/deck-groups", ("name",)),
        ("/api/binders", ("name", "description")),
        ("/api/orders", ("order_number",)),
        ("/api/batches", ("name", "batch_uuid")),
        ("/api/views", ("name",)),
        ("/api/wishlist", ("notes",)),
        ("/api/ingest2/images", ("filename", "md5")),
    ):
        for row in _ok(alice, path):
            marks.update(str(row[k]) for k in keys if row.get(k))
    assert len(marks) >= 8, f"alice's markers are too few to prove anything: {marks}"
    return marks


def _all_get_paths(ids):
    paths = [p for p, _ in LIST_FAMILIES.values()]
    paths += [t.format(**ids) for t in [*BY_ID.values(), *CHILD_LISTS.values()]]
    paths += ["/api/settings", "/api/sets/index", "/api/sealed/collection/stats"]
    return paths


def test_none_of_alices_strings_reach_b_over_the_api(alice, bobby, ids):
    marks = _alice_markers(alice)
    leaks = []
    for path in _all_get_paths(ids):
        _, body = bobby.raw("GET", path)
        text = body.decode("utf-8", "replace")
        leaks += [(path, m) for m in marks if m in text]
    assert not leaks, f"bobby was served alice's data: {leaks[:10]}"


# --- pages ----------------------------------------------------------------------

def _page_urls(ids):
    samples = {
        "/deck-builder/": f"/deck-builder/{ids['deck']}",
        "/decks/": f"/decks/{ids['deck']}",
        "/deck-groups/": f"/deck-groups/{ids['group']}",
        "/sets/": "/sets/dsk",
        "/card/": "/card/dsk/1",
        "/batches/": f"/batches/{ids['batch']}",
        "/orders/": f"/orders/{ids['order']}",
    }
    return [samples[r.path] if r.parametrized else r.path for r in PAGE_ROUTES]


@pytest.fixture(scope="module")
def secrets(alice):
    """Names no catalogue, template or static page carries, so finding one is a leak."""
    status, deck = alice.json("POST", "/api/decks", {"name": "ntly-secret-deck", "format": "commander"})
    assert status == 201, deck
    status, binder = alice.json("POST", "/api/binders", {"name": "ntly-secret-binder"})
    assert status == 201, binder
    return ["ntly-secret-deck", "ntly-secret-binder"]


def test_every_page_renders_for_both_tenants_and_leaks_nothing(alice, bobby, ids, secrets):
    embedded_for_alice = set()
    for url in _page_urls(ids):
        for tenant in (alice, bobby):
            status, _ = tenant.raw("GET", url)
            assert status == 200, f"{tenant.email} GET {url} -> {status}"
        theirs = bobby.text(url)
        leaked = [m for m in secrets if m in theirs]
        assert not leaked, f"bobby's {url} embeds alice's data: {leaked}"
        embedded_for_alice |= {m for m in secrets if m in alice.text(url)}
    assert embedded_for_alice, "control arm: no page embedded any of alice's data, so the sweep proves nothing"


def test_decks_page_embeds_only_the_requesting_tenants_decks(alice, bobby, secrets):
    assert "ntly-secret-deck" in alice.text("/decks"), "control arm: alice's /decks page lacks her deck"
    assert "ntly-secret-deck" not in bobby.text("/decks")


# --- writes land in the writer's file ---------------------------------------------

def test_writes_land_only_in_the_writers_file(alice, bobby):
    a_before = _ok(alice, "/api/collection?limit=1")
    printing = a_before["rows"][0]["printing_id"]

    status, _ = alice.json("POST", "/api/collection", {"printing_id": printing, "finish": "nonfoil"})
    assert status in (200, 201)
    status, mine = alice.json("POST", "/api/binders", {"name": "ntly-alice-only"})
    assert status == 201, mine
    status, theirs = bobby.json("POST", "/api/binders", {"name": "ntly-bobby-only"})
    assert status == 201, theirs

    a_after, b_after = _ok(alice, "/api/collection?limit=1"), _ok(bobby, "/api/collection?limit=1")
    assert a_after["total_qty"] == a_before["total_qty"] + 1
    assert b_after["total_qty"] == 0, "alice's added copy appeared for bobby"

    a_names = {b["name"] for b in _ok(alice, "/api/binders")}
    b_names = {b["name"] for b in _ok(bobby, "/api/binders")}
    assert "ntly-alice-only" in a_names and "ntly-bobby-only" not in a_names
    assert b_names == {"ntly-bobby-only"}


def test_b_cannot_change_or_delete_a(alice, bobby, ids):
    before = json.dumps(_ok(alice, f"/api/decks/{ids['deck']}"), sort_keys=True)
    for method, path, data in (
        ("PUT", f"/api/decks/{ids['deck']}", {"name": "hijacked"}),
        ("DELETE", f"/api/decks/{ids['deck']}", None),
        ("PUT", f"/api/binders/{ids['binder']}", {"name": "hijacked"}),
        ("DELETE", f"/api/binders/{ids['binder']}", None),
    ):
        status, _ = bobby.json(method, path, data)
        assert status == 404, f"bobby {method} {path} -> {status}"
    assert json.dumps(_ok(alice, f"/api/decks/{ids['deck']}"), sort_keys=True) == before
    assert _ok(alice, f"/api/binders/{ids['binder']}")["name"] != "hijacked"
