"""HTTP response semantics: cache policy, validators, gzip, ranges (de-dai).

Two halves.  The first drives the pure decisions in ``mtg_collector.http_cache``
directly.  The second binds a real ``CrackPackHandler`` on port 0 and speaks
HTTP to it, because the defect this replaces was not in any decision -- each
call site's Cache-Control string was individually defensible -- it was in what
actually went out on the wire.  Tier 1: no container, no network, no fixed port.

The acceptance criteria for de-dai are each a test here:
  * a document response revalidates (If-None-Match -> 304)
  * a document's Cache-Control has no multi-hour max-age
  * the immutable asset path still returns immutable
  * gzip is negotiated when the client offers it
  * a page changed on disk is served changed on the next request, no restart
"""

import contextlib
import gzip
import http.client
import threading
from functools import partial

import pytest

from mtg_collector.cli import crack_pack_server as cps
from mtg_collector.http_cache import (
    CACHE_API,
    CACHE_DOCUMENT,
    CACHE_IMMUTABLE,
    RangeNotSatisfiable,
    compute_etag,
    etag_matches,
    negotiate_gzip,
    parse_range,
)

# Comfortably over GZIP_MIN_BYTES and compressible, so "was it gzipped" is a
# question about negotiation rather than about the size threshold.
PAGE = "<!doctype html><title>t</title>" + ("<p>hello</p>" * 400)


# ── The decisions, without a socket ─────────────────────────────────────────


def test_document_policy_has_no_multi_hour_max_age():
    """The exact shape of the bug: an edge holding a document for a day."""
    assert "max-age" not in CACHE_DOCUMENT
    assert "no-cache" in CACHE_DOCUMENT


def test_api_policy_is_private():
    """Collection data must not land in a shared edge cache."""
    assert CACHE_API.startswith("private")


def test_immutable_policy_is_unchanged():
    """The bead's instruction was that the one path already doing this right
    keeps its behaviour exactly. Not `immutable` in spirit -- byte for byte."""
    assert CACHE_IMMUTABLE == "public, max-age=86400, immutable"


def test_etag_varies_with_encoding():
    """Identity and gzip are different representations and get different tags.

    One tag for two bodies is how a cache serves gzipped bytes to a client that
    asked for none.
    """
    body = b"x" * 4096
    assert compute_etag(body) != compute_etag(body, encoding="gzip")


def test_etag_is_content_derived():
    assert compute_etag(b"a") != compute_etag(b"b")
    assert compute_etag(b"a") == compute_etag(b"a")


@pytest.mark.parametrize("header", ['"abc"', '*', 'W/"abc"', '"zzz", "abc"'])
def test_if_none_match_hits(header):
    assert etag_matches(header, '"abc"')


@pytest.mark.parametrize("header", [None, "", '"zzz"', '"abc-gzip"'])
def test_if_none_match_misses(header):
    assert not etag_matches(header, '"abc"')


def test_gzip_declined_for_small_and_incompressible():
    assert not negotiate_gzip("gzip", "application/json", 10)
    assert not negotiate_gzip("gzip", "image/png", 100_000)
    assert not negotiate_gzip("", "application/json", 100_000)
    assert negotiate_gzip("gzip, deflate", "application/json", 100_000)


def test_range_parsing():
    assert parse_range(None, 100) is None
    assert parse_range("bytes=0-9", 100) == (0, 9)
    assert parse_range("bytes=90-", 100) == (90, 99)
    assert parse_range("bytes=-10", 100) == (90, 99)
    # A suffix longer than the representation is the whole representation.
    assert parse_range("bytes=-500", 100) == (0, 99)
    # Past the end is clamped, not an error -- the range still lands inside.
    assert parse_range("bytes=50-500", 100) == (50, 99)


@pytest.mark.parametrize("header", ["items=0-9", "bytes=0-9,20-29", "garbage", "bytes=-"])
def test_unparseable_range_is_ignored_not_an_error(header):
    """RFC 9110: a Range we cannot act on is ignored, and the whole body is a
    correct response to it.  Only a well-formed unsatisfiable one is a 416."""
    assert parse_range(header, 100) is None


@pytest.mark.parametrize("header", ["bytes=100-", "bytes=200-300"])
def test_range_past_the_end_is_416(header):
    with pytest.raises(RangeNotSatisfiable):
        parse_range(header, 100)


def test_any_range_of_an_empty_representation_is_416():
    with pytest.raises(RangeNotSatisfiable):
        parse_range("bytes=0-0", 0)


# ── The wire ────────────────────────────────────────────────────────────────


@pytest.fixture
def server(tmp_path):
    """A real handler on a real socket, serving ``tmp_path`` as its static dir.

    ``generator`` and ``db_path`` are unused by every path exercised here, so
    nothing needs a database: this stays in the no-container tier.
    """
    (tmp_path / "index.html").write_text(PAGE)
    handler = partial(cps.CrackPackHandler, None, tmp_path, str(tmp_path / "nodb.sqlite"))
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


def test_document_carries_a_validator_and_revalidates(server):
    """The headline criterion: the edge gets something to revalidate against."""
    status, headers, _ = _get(server)
    assert status == 200
    assert headers["Cache-Control"] == CACHE_DOCUMENT
    etag = headers["ETag"]
    assert etag

    status, headers, body = _get(server, headers={"If-None-Match": etag})
    assert status == 304
    assert body == b""
    # A 304 must still carry the policy and the tag, or the cache it is
    # answering has nothing to write back into its own entry.
    assert headers["ETag"] == etag
    assert headers["Cache-Control"] == CACHE_DOCUMENT


def test_a_page_changed_on_disk_is_served_changed_with_no_restart(server, tmp_path):
    """The failure the whole bead is about, at origin scale."""
    _, headers, _ = _get(server)
    before = headers["ETag"]

    (tmp_path / "index.html").write_text(PAGE + "<!-- deployed -->")

    status, headers, body = _get(server, headers={"If-None-Match": before})
    assert status == 200, "a stale validator must not be honoured after a deploy"
    assert headers["ETag"] != before
    assert b"deployed" in body


def test_gzip_is_negotiated(server):
    status, headers, body = _get(server, headers={"Accept-Encoding": "gzip"})
    assert status == 200
    assert headers["Content-Encoding"] == "gzip"
    assert gzip.decompress(body).decode() == PAGE
    assert headers["Vary"] == "Accept-Encoding"
    # Advertising ranges over a compressed body would invite a range request
    # against a representation whose ETag we never minted.
    assert "Accept-Ranges" not in headers


def test_identity_is_served_when_gzip_is_not_offered(server):
    status, headers, body = _get(server)
    assert status == 200
    assert "Content-Encoding" not in headers
    assert body.decode() == PAGE
    assert headers["Accept-Ranges"] == "bytes"


def test_the_two_encodings_do_not_share_an_etag(server):
    _, identity, _ = _get(server)
    _, gzipped, _ = _get(server, headers={"Accept-Encoding": "gzip"})
    assert identity["ETag"] != gzipped["ETag"]
    # And each still revalidates against its own.
    status, _, _ = _get(server, headers={"Accept-Encoding": "gzip",
                                         "If-None-Match": gzipped["ETag"]})
    assert status == 304


def test_range_request_returns_the_slice(server):
    status, headers, body = _get(server, headers={"Range": "bytes=0-9"})
    assert status == 206
    assert body == PAGE.encode()[:10]
    assert headers["Content-Range"] == f"bytes 0-9/{len(PAGE)}"
    assert headers["Content-Length"] == "10"


def test_range_forces_identity_even_when_gzip_is_offered(server):
    """A range is a range of the representation the ETag names."""
    status, headers, body = _get(server, headers={"Range": "bytes=0-9",
                                                  "Accept-Encoding": "gzip"})
    assert status == 206
    assert "Content-Encoding" not in headers
    assert body == PAGE.encode()[:10]


def test_unsatisfiable_range_is_416(server):
    status, headers, _ = _get(server, headers={"Range": f"bytes={len(PAGE) + 10}-"})
    assert status == 416
    assert headers["Content-Range"] == f"bytes */{len(PAGE)}"


def test_static_assets_revalidate_too(server, tmp_path):
    """/static/* URLs carry no content hash, so a long max-age is the same bug
    the documents had -- a stale style sheet outlives a deploy just as well."""
    (tmp_path / "app.css").write_text("body{color:red}" * 200)
    status, headers, _ = _get(server, "/static/app.css")
    assert status == 200
    assert headers["Cache-Control"] == CACHE_DOCUMENT
    assert headers["ETag"]


def test_a_missing_static_file_is_a_404_with_no_validator(server):
    status, headers, _ = _get(server, "/static/nope.css")
    assert status == 404
    assert "ETag" not in headers, "an error body is not a representation to cache"


def test_api_errors_carry_the_api_policy(server):
    """Error JSON goes out through the same door and is never publicly cached."""
    status, headers, _ = _get(server, "/static/nope.css")
    assert status == 404
    assert headers["Cache-Control"] == CACHE_API
