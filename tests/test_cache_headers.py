"""What each kind of response tells a cache it may do with it.

Tier 1 — no container, no network. Every response is written into a BytesIO
standing in for the socket, the way `test_page_path_normalization.py` drives
`do_GET` against a handler built without one.

On 2026-08-25 six deploys landed and magic.dumpster.cards showed none of them.
Every page was served `public, max-age=86400` with no validator, so Cloudflare
held a copy it had no way to notice was stale, and a hard refresh — which only
defeats the *browser's* cache — could not shift it. It took a manual purge.

The distinction these pin is between a URL a deploy rewrites in place (a
document, its CSS and JS) and a URL that names its own bytes (an ingest image).
The first must revalidate; the second is immutable and stays that way.
"""

import email.message
import http.client
import io
from pathlib import Path
from unittest.mock import patch

import pytest

from mtg_collector.cli import crack_pack_server as cps

STATIC = Path(cps.__file__).resolve().parent.parent / "static"


def _handler(request_headers=None):
    """A handler with a BytesIO for a socket and nothing else it doesn't need."""
    h = object.__new__(cps.CrackPackHandler)
    h.static_dir = STATIC
    h.path = "/collection"
    h.command = "GET"
    h.requestline = "GET /collection HTTP/1.1"
    h.request_version = "HTTP/1.1"
    h.client_address = ("127.0.0.1", 0)
    h.headers = email.message.Message()
    for name, value in (request_headers or {}).items():
        h.headers[name] = value
    h.wfile = io.BytesIO()
    return h


def _response(h):
    """(status, headers, body) as written to the wire."""
    head, _, body = h.wfile.getvalue().partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    status = int(lines[0].split()[1])
    headers = http.client.parse_headers(io.BytesIO(b"\r\n".join(lines[1:]) + b"\r\n\r\n"))
    return status, headers, body


def _serve(filename="collection.html", request_headers=None):
    h = _handler(request_headers)
    h._serve_static(filename)
    return _response(h)


def _max_age(cache_control):
    """The max-age in seconds, or None if the header names none."""
    for part in cache_control.split(","):
        part = part.strip()
        if part.startswith("max-age="):
            return int(part.split("=", 1)[1])
    return None


PAGES = ["collection.html", "sets.html", "index.html", "deck_builder.html"]


@pytest.mark.parametrize("page", PAGES)
def test_a_page_is_not_cacheable_for_longer_than_a_few_minutes(page):
    _, headers, _ = _serve(page)
    max_age = _max_age(headers["Cache-Control"])
    assert max_age is None or max_age <= 300, headers["Cache-Control"]


@pytest.mark.parametrize("page", PAGES)
def test_a_page_carries_a_validator(page):
    """Without one the edge has nothing to revalidate against, which is the bug."""
    _, headers, _ = _serve(page)
    assert headers["ETag"]


def test_the_css_and_js_a_page_names_revalidate_too():
    """They sit at a stable URL a deploy rewrites, exactly like the document."""
    _, headers, _ = _serve("shared.css")
    max_age = _max_age(headers["Cache-Control"])
    assert max_age is None or max_age <= 300, headers["Cache-Control"]
    assert headers["ETag"]


def test_a_matching_conditional_request_is_a_304_with_no_body():
    _, headers, body = _serve()
    status, again, empty = _serve(request_headers={"If-None-Match": headers["ETag"]})
    assert status == 304
    assert empty == b""
    assert again["ETag"] == headers["ETag"]
    assert body != b""


def test_a_stale_validator_gets_the_document():
    status, _, body = _serve(request_headers={"If-None-Match": 'W/"stale"'})
    assert status == 200
    assert body != b""


def test_one_of_several_offered_validators_still_matches():
    """A client may present a list; the match is per-entry, not on the string."""
    _, headers, _ = _serve()
    offered = 'W/"stale", %s' % headers["ETag"]
    status, _, _ = _serve(request_headers={"If-None-Match": offered})
    assert status == 304


def test_the_validator_does_not_depend_on_whether_the_body_was_gzipped():
    """Same document either way, so a client that switches keeps its 304."""
    _, plain, _ = _serve()
    _, gzipped, body = _serve(request_headers={"Accept-Encoding": "gzip"})
    assert gzipped["Content-Encoding"] == "gzip"
    assert gzipped["ETag"] == plain["ETag"]


def test_content_addressed_bytes_keep_their_immutable_year(tmp_path):
    """The other case, and it must not be swept up in the rule above."""
    (tmp_path / "abc123.jpg").write_bytes(b"\xff\xd8\xff" + b"x" * 64)
    h = _handler()
    with patch.object(cps, "_get_ingest_images_dir", return_value=tmp_path):
        h._api_ingest_serve_image("abc123.jpg")
    _, headers, _ = _response(h)
    assert headers["Cache-Control"] == "public, max-age=86400, immutable"


def test_an_api_answer_is_never_stored():
    """A day-old catalogue reads exactly like a broken one."""
    h = _handler()
    h._send_json({"cards": []})
    _, headers, _ = _response(h)
    assert _max_age(headers["Cache-Control"]) is None
    assert "no-store" in headers["Cache-Control"]
