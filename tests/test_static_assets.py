"""Content-addressed /static/* URLs: the digest, the rewrite, the promise (de-l23).

Tier 1 — no container, no network, no fixed port.

Two halves, the same shape as `test_http_cache.py`. The first drives
`mtg_collector.static_assets` directly. The second binds a real
`CrackPackHandler` on port 0, because what this bead changes is what goes out on
the wire: a page whose asset URLs no client can resolve is a page that renders
unstyled, and no unit test of a digest would notice.

The acceptance criteria for de-l23 are each a test here:
  * a page's asset references come back carrying a digest
  * every URL a served page names is a URL that same server answers
  * a hashed URL is answered `immutable` with a max-age worth having
  * an unhashed /static URL still revalidates, exactly as de-dai left it
  * an asset changed on disk changes the URL, with no restart and no build step
  * a URL whose digest is stale is a 404, never today's bytes under a promise
"""

import contextlib
import http.client
import re
import sqlite3
import threading
from functools import partial

import pytest

from mtg_collector.cli import crack_pack_server as cps
from mtg_collector.db.schema import init_db
from mtg_collector.http_cache import CACHE_DOCUMENT, CACHE_HASHED_ASSET
from mtg_collector.static_assets import DIGEST_LENGTH, AssetHasher

CSS = "body{color:red}"
PAGE = (
    '<!doctype html><link rel="stylesheet" href="/static/app.css">'
    '<script src="/static/vendor/chart.umd.min.js"></script>'
    '<link rel="icon" href="/static/favicon.ico">'
)


@pytest.fixture
def static_dir(tmp_path):
    """A static tree with the shapes that have bitten this repo before.

    A vendored stylesheet beside its own `fonts/` directory, a name with dots
    in it (`chart.umd.min.js`), and a page that references all of them.
    """
    (tmp_path / "app.css").write_text(CSS)
    (tmp_path / "index.html").write_text(PAGE)
    (tmp_path / "favicon.ico").write_bytes(b"\x00icon")
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    (vendor / "chart.umd.min.js").write_text("chart()")
    keyrune = vendor / "keyrune"
    (keyrune / "fonts").mkdir(parents=True)
    (keyrune / "keyrune.min.css").write_text("@font-face{src:url('fonts/k.woff2')}")
    (keyrune / "fonts" / "k.woff2").write_bytes(b"font")
    return tmp_path


# ── the digest and the two translations ─────────────────────────────────────


def test_the_url_carries_the_digest_of_the_bytes(static_dir):
    hasher = AssetHasher(static_dir)
    url = hasher.hashed_url("app.css")
    assert re.fullmatch(rf"/static/app\.[0-9a-f]{{{DIGEST_LENGTH}}}\.css", url), url


def test_a_hashed_url_stays_in_its_own_directory(static_dir):
    """`keyrune.min.css` asks for `url('fonts/k.woff2')`, which resolves against
    the directory the stylesheet is served from. A digest in a path segment
    would send every glyph request somewhere that does not exist — the same 404
    `test_vendored_fonts.py` exists to prevent, reached from the other side."""
    url = AssetHasher(static_dir).hashed_url("vendor/keyrune/keyrune.min.css")
    assert url.startswith("/static/vendor/keyrune/keyrune.min.")
    assert url.endswith(".css")


def test_a_name_with_dots_keeps_every_one_of_them(static_dir):
    """`chart.umd.min.js` round-trips: the digest goes before the last suffix,
    and reading it back must not mistake `umd` or `min` for one."""
    hasher = AssetHasher(static_dir)
    url = hasher.hashed_url("vendor/chart.umd.min.js")
    asset = hasher.resolve(url.removeprefix("/static/"))
    assert asset.content_addressed
    assert asset.path == static_dir / "vendor" / "chart.umd.min.js"


def test_html_is_never_content_addressed(static_dir):
    """A document is rewritten on the way out, so its bytes on the wire change
    when an asset it names changes while its own file does not. A digest taken
    from the file would be a promise about bytes nobody sent."""
    hasher = AssetHasher(static_dir)
    assert hasher.hashed_url("index.html") is None
    assert hasher.resolve("index.0123456789abcdef.html") is None


def test_the_rewrite_hashes_what_it_can_and_leaves_the_rest(static_dir):
    hasher = AssetHasher(static_dir)
    out = hasher.rewrite(
        b'<img src="/static/app.css"><img src="/static/gone.css">'
    ).decode()
    assert hasher.hashed_url("app.css") in out
    assert '"/static/gone.css"' in out, (
        "a reference naming no file must survive untouched — it is the visible "
        "404 it always was, not a silent rewrite to something else"
    )


def test_an_unhashed_url_still_names_its_file(static_dir):
    """Every URL that worked before this change still works."""
    asset = AssetHasher(static_dir).resolve("app.css")
    assert asset.path == static_dir / "app.css"
    assert not asset.content_addressed


def test_a_path_out_of_the_static_tree_resolves_to_nothing(static_dir):
    assert AssetHasher(static_dir).resolve("../secrets.css") is None


def test_a_stale_digest_resolves_to_nothing(static_dir):
    hasher = AssetHasher(static_dir)
    stale = hasher.hashed_url("app.css").removeprefix("/static/")
    (static_dir / "app.css").write_text(CSS + "/* deployed */")
    assert hasher.resolve(stale) is None, (
        "serving current bytes under a URL that asked for older ones is how a "
        "client ends up holding the wrong thing under a promise it cannot "
        "revalidate away"
    )
    assert hasher.resolve(hasher.hashed_url("app.css").removeprefix("/static/"))


# ── the wire ────────────────────────────────────────────────────────────────


@pytest.fixture
def server(static_dir):
    handler = partial(cps.CrackPackHandler, None, static_dir, str(static_dir / "nodb.sqlite"))
    httpd = cps.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        stopper = threading.Thread(target=httpd.shutdown, daemon=True)
        stopper.start()
        stopper.join(timeout=5)
        with contextlib.suppress(Exception):
            httpd.server_close()
        thread.join(timeout=5)


def _get(server, path="/", headers=None):
    conn = http.client.HTTPConnection(*server.server_address, timeout=10)
    try:
        conn.request("GET", path, headers=headers or {})
        resp = conn.getresponse()
        return resp.status, dict(resp.getheaders()), resp.read()
    finally:
        conn.close()


def _referenced(body: bytes) -> list[str]:
    return re.findall(r'"(/static/[^"]+)"', body.decode())


def test_a_page_names_hashed_urls(server):
    _, _, body = _get(server)
    named = _referenced(body)
    assert named, "the page under test names no assets"
    for url in named:
        assert re.search(rf"\.[0-9a-f]{{{DIGEST_LENGTH}}}\.", url), f"{url} carries no digest"


def test_every_url_the_page_names_is_one_this_server_answers(server):
    """The failure mode worth a socket: a rewritten page renders unstyled and
    nothing in the server logs looks wrong."""
    _, _, body = _get(server)
    for url in _referenced(body):
        status, headers, content = _get(server, url)
        assert status == 200, f"{url} -> {status}"
        assert content
        assert headers["Cache-Control"] == CACHE_HASHED_ASSET


def test_a_hashed_asset_is_promised_a_year(server):
    _, _, body = _get(server)
    url = next(u for u in _referenced(body) if u.endswith(".css"))
    _, headers, _ = _get(server, url)
    assert headers["Cache-Control"] == "public, max-age=31536000, immutable"
    assert headers["ETag"], "immutable is a promise, not an excuse to drop the validator"


def test_an_unhashed_asset_url_still_revalidates(server):
    """de-dai's rule for a URL with no digest is unchanged: `no-cache`, and a
    validator to answer with."""
    status, headers, _ = _get(server, "/static/app.css")
    assert status == 200
    assert headers["Cache-Control"] == CACHE_DOCUMENT
    assert headers["ETag"]


def test_an_asset_changed_on_disk_changes_its_url_with_no_restart(server, static_dir):
    """No build step: the digest is minted as the document goes out, so an edit
    is live on the next page load and the old URL stops being answered."""
    _, _, before = _get(server)
    old = next(u for u in _referenced(before) if u.endswith(".css"))
    assert _get(server, old)[0] == 200

    (static_dir / "app.css").write_text(CSS + "/* deployed */")

    _, _, after = _get(server)
    new = next(u for u in _referenced(after) if u.endswith(".css"))
    assert new != old
    assert _get(server, new)[0] == 200
    assert _get(server, old)[0] == 404, (
        "the old URL promised bytes this server no longer has; answering it "
        "with the new ones is the promise broken silently"
    )


def test_the_document_itself_is_never_immutable(server):
    """Documents are what a deploy needs re-fetched; that is the whole of de-dai."""
    _, headers, _ = _get(server)
    assert headers["Cache-Control"] == CACHE_DOCUMENT


def test_a_page_served_with_init_data_is_rewritten_too(server, static_dir):
    """`/decks` goes through `_serve_static_with_data`, a second door into the
    same HTML. A rewrite wired into only one of them leaves one page unstyled,
    and it is the door with the splice in it — the one easiest to forget."""
    conn = sqlite3.connect(static_dir / "nodb.sqlite")
    init_db(conn)
    conn.commit()
    conn.close()
    (static_dir / "decks.html").write_text(
        '<script>const D = /*INIT_DATA*/;</script>'
        '<link rel="stylesheet" href="/static/app.css">'
    )
    status, headers, body = _get(server, "/decks")
    assert status == 200
    assert b"/*INIT_DATA*/" not in body
    assert headers["Cache-Control"] == CACHE_DOCUMENT
    for url in _referenced(body):
        assert re.search(rf"\.[0-9a-f]{{{DIGEST_LENGTH}}}\.", url), f"{url} carries no digest"
        assert _get(server, url)[0] == 200
