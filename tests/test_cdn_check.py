"""The CDN deploy check must be seen going RED, not just green (de-dai).

`deploy/cdn-check.sh` exists because every check run on the evening of
2026-08-25 passed while the public site was a day stale. A check that has only
ever been observed passing is not known to work — that is the entire defect it
replaces — so most of what is below drives it into each failure it claims to
catch and asserts on the exit status and the message.

`curl` is the script's only external call, so it is stubbed with a PATH shim
that records its argv and replays a canned header dump per invocation. That
keeps this in the unit tier: no network, no Cloudflare, no origin, and no way
for a test to reach the real site.
"""

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECK = REPO_ROOT / "deploy" / "cdn-check.sh"

# Replays responses/N.txt for the Nth call, so a canned conversation lines up
# with the script's fixed call order: origin, edge, conditional, gzip, then the
# document body and the two sides of one asset it names (de-l23).
CURL_STUB = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$CURL_CALL_LOG"
n=$(( $(cat "$CURL_SEQ" 2>/dev/null || echo 0) + 1 ))
printf '%s' "$n" > "$CURL_SEQ"
if [ -f "$CURL_RESPONSES/$n.txt" ]; then cat "$CURL_RESPONSES/$n.txt"; fi
exit "${CURL_RC:-0}"
"""

ETAG = '"1f2e3d4c5b6a7988"'


def _dump(status="200", etag=ETAG, cache="public, no-cache", extra=()):
    """A response header block as curl -D - would write it."""
    lines = [f"HTTP/2 {status}", "content-type: text/html; charset=utf-8"]
    if etag:
        lines.append(f"etag: {etag}")
    if cache:
        lines.append(f"cache-control: {cache}")
    lines.extend(extra)
    return "\r\n".join(lines) + "\r\n\r\n"


#: One content-addressed asset URL, as the server now rewrites references into
#: (de-l23), and the headers a correct edge answers it with.
ASSET_URL = "/static/shared.0123456789abcdef.css"
ASSET_ETAG = '"0123456789abcdef0123456789abcdef"'
ASSET_CACHE = "public, max-age=31536000, immutable"
DOCUMENT_BODY = f'<!doctype html><link rel="stylesheet" href="{ASSET_URL}">'

# The happy path: origin and edge agree, the edge revalidates, gzip negotiated,
# and the asset the document names is immutable and identical on both sides.
GREEN = {
    1: _dump(),
    2: _dump(),
    3: _dump(status="304"),
    4: _dump(extra=["content-encoding: gzip"]),
    5: DOCUMENT_BODY,
    6: _dump(etag=ASSET_ETAG, cache=ASSET_CACHE),
    7: _dump(etag=ASSET_ETAG, cache=ASSET_CACHE),
}


def _run(tmp_path, responses, *, env=None, args=()):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "curl"
    stub.write_text(CURL_STUB)
    stub.chmod(0o755)

    resp_dir = tmp_path / "responses"
    resp_dir.mkdir(exist_ok=True)
    for n, text in responses.items():
        (resp_dir / f"{n}.txt").write_text(text)

    call_log = tmp_path / "curl.log"
    child = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "CURL_CALL_LOG": str(call_log),
        "CURL_SEQ": str(tmp_path / "seq"),
        "CURL_RESPONSES": str(resp_dir),
    }
    child.pop("CF_ACCESS_CLIENT_ID", None)
    child.pop("CF_ACCESS_CLIENT_SECRET", None)
    child.update(env or {})

    proc = subprocess.run(
        ["bash", str(CHECK), *args],
        capture_output=True, text=True, env=child, cwd=tmp_path,
    )
    calls = call_log.read_text() if call_log.exists() else ""
    return proc, calls


# ── Green, and what green had to have asked ─────────────────────────────────


def test_green_run_passes(tmp_path):
    proc, _ = _run(tmp_path, GREEN)
    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout


def test_green_run_actually_traversed_the_cdn(tmp_path):
    """The point of the script. A pass that never left the box is the bug."""
    proc, calls = _run(tmp_path, GREEN)
    assert proc.returncode == 0, proc.stderr
    assert "https://magic.dumpster.cards/" in calls
    assert "https://localhost:8081/" in calls
    # Both sides compared as the same representation, or the comparison is a
    # coin toss against whichever encoding each hop happened to pick.
    assert calls.count("Accept-Encoding: identity") >= 2


def test_it_cannot_pass_without_asking_both_sides(tmp_path):
    """No configuration reduces this to a one-sided check."""
    proc, calls = _run(tmp_path, GREEN, args=["--url", "https://edge.example",
                                              "--origin", "https://origin.example"])
    assert proc.returncode == 0, proc.stderr
    assert "https://edge.example/" in calls
    assert "https://origin.example/" in calls


# ── Every failure it claims to catch ────────────────────────────────────────


def test_stale_edge_is_caught(tmp_path):
    """THE outage: the edge serving a different document than the origin."""
    responses = {**GREEN, 2: _dump(etag='"deadbeefdeadbeef"')}
    proc, _ = _run(tmp_path, responses)
    assert proc.returncode == 1
    assert "DIFFERENT document" in proc.stderr
    assert "not visible to users" in proc.stderr


def test_long_max_age_on_a_document_is_caught(tmp_path):
    """The header that caused it, in case anything ever puts it back."""
    responses = {**GREEN, 2: _dump(cache="public, max-age=86400")}
    proc, _ = _run(tmp_path, responses)
    assert proc.returncode == 1
    assert "86400s" in proc.stderr


def test_a_short_max_age_is_still_legal(tmp_path):
    """The threshold is a multi-hour hold, not any max-age at all."""
    responses = {**GREEN, 2: _dump(cache="public, max-age=30")}
    proc, _ = _run(tmp_path, responses)
    assert proc.returncode == 0, proc.stderr


def test_s_maxage_is_not_mistaken_for_max_age(tmp_path):
    """`s-maxage` and `stale-while-revalidate=86400` are different directives;
    reading either as max-age would be a false red on a correct deploy."""
    responses = {**GREEN, 2: _dump(cache="public, no-cache, stale-while-revalidate=86400")}
    proc, _ = _run(tmp_path, responses)
    assert proc.returncode == 0, proc.stderr


def test_missing_validator_at_the_edge_is_caught(tmp_path):
    responses = {**GREEN, 2: _dump(etag=None)}
    proc, _ = _run(tmp_path, responses)
    assert proc.returncode == 1
    assert "no ETag" in proc.stderr


def test_missing_validator_at_the_origin_is_caught(tmp_path):
    responses = {**GREEN, 1: _dump(etag=None)}
    proc, _ = _run(tmp_path, responses)
    assert proc.returncode == 1
    assert "origin served no ETag" in proc.stderr


def test_edge_that_does_not_revalidate_is_caught(tmp_path):
    """A 200 to a conditional request means every page load is a full transfer."""
    responses = {**GREEN, 3: _dump()}
    proc, _ = _run(tmp_path, responses)
    assert proc.returncode == 1
    assert "not 304" in proc.stderr


def test_edge_that_does_not_compress_is_caught(tmp_path):
    responses = {**GREEN, 4: _dump()}
    proc, _ = _run(tmp_path, responses)
    assert proc.returncode == 1
    assert "content-encoding" in proc.stderr


def test_dead_origin_is_caught(tmp_path):
    proc, _ = _run(tmp_path, {1: "curl: (7) Failed to connect to localhost port 8081\n"})
    assert proc.returncode == 1
    assert "not 200" in proc.stderr
    assert "Failed to connect" in proc.stderr, "the transport error must reach the reader"


def test_dead_edge_is_caught(tmp_path):
    proc, _ = _run(tmp_path, {**GREEN, 2: _dump(status="502", etag=None, cache=None)})
    assert proc.returncode == 1
    assert "'502'" in proc.stderr


# ── The asset the document names (de-l23) ───────────────────────────────────


def test_a_document_naming_no_hashed_asset_is_caught(tmp_path):
    """An origin that stopped rewriting references is a silent regression: the
    site still works, and every asset goes back to costing a round trip."""
    proc, _ = _run(tmp_path, {**GREEN, 5: '<link rel="stylesheet" href="/static/shared.css">'})
    assert proc.returncode == 1
    assert "names no content-addressed asset" in proc.stderr


def test_an_asset_the_edge_cannot_serve_is_caught(tmp_path):
    """The document names it, so a 404 here is every user's page unstyled."""
    proc, _ = _run(tmp_path, {**GREEN, 7: _dump(status="404", etag=None, cache=None)})
    assert proc.returncode == 1
    assert "'404'" in proc.stderr


def test_an_asset_missing_at_the_origin_is_caught(tmp_path):
    proc, _ = _run(tmp_path, {**GREEN, 6: _dump(status="404", etag=None, cache=None)})
    assert proc.returncode == 1
    assert "renders unstyled" in proc.stderr


def test_an_asset_not_served_immutable_is_caught(tmp_path):
    """The digest in the URL is the whole reason the long window is correct;
    paying for the URL and taking none of the benefit is the regression."""
    proc, _ = _run(tmp_path, {**GREEN, 7: _dump(etag=ASSET_ETAG, cache="public, no-cache")})
    assert proc.returncode == 1
    assert "content-addressed asset is served" in proc.stderr


def test_an_edge_holding_different_bytes_for_a_hashed_url_is_caught(tmp_path):
    """A digest names one byte string. Under a year-long promise, an edge
    holding another is a cache nobody can revalidate out of."""
    proc, _ = _run(tmp_path, {**GREEN, 7: _dump(etag='"deadbeefdeadbeefdeadbeefdeadbeef"',
                                                cache=ASSET_CACHE)})
    assert proc.returncode == 1
    assert "DIFFERENT bytes" in proc.stderr


# ── The Access wall, diagnosed by name ──────────────────────────────────────


def test_access_login_page_is_named_not_reported_as_a_mismatch(tmp_path):
    """Undiagnosed, this reads as "the ETags differ" and sends the reader to
    the deploy and the cache, neither of which is wrong."""
    wall = ("HTTP/2 302\r\n"
            "location: https://ryangantt.cloudflareaccess.com/cdn-cgi/access/login/magic\r\n\r\n")
    proc, _ = _run(tmp_path, {**GREEN, 2: wall})
    assert proc.returncode == 1
    assert "Cloudflare Access login page" in proc.stderr
    assert "CF_ACCESS_CLIENT_ID" in proc.stderr
    assert "DIFFERENT document" not in proc.stderr


def test_service_token_is_sent_on_every_public_request(tmp_path):
    proc, calls = _run(tmp_path, GREEN, env={
        "CF_ACCESS_CLIENT_ID": "id.access",
        "CF_ACCESS_CLIENT_SECRET": "sekrit",
    })
    assert proc.returncode == 0, proc.stderr
    public_calls = [line for line in calls.splitlines() if "magic.dumpster.cards" in line]
    assert len(public_calls) == 5, f"expected five edge requests, got {public_calls}"
    assert all("CF-Access-Client-Id: id.access" in line for line in public_calls)
    # And never at the origin, which is not behind Access.
    origin_calls = [line for line in calls.splitlines() if "localhost:8081" in line]
    assert all("CF-Access-Client-Id" not in line for line in origin_calls)


# ── Argument handling ───────────────────────────────────────────────────────


def test_unknown_argument_is_rejected_rather_than_ignored(tmp_path):
    proc, calls = _run(tmp_path, GREEN, args=["--purge"])
    assert proc.returncode == 2
    assert "unknown argument" in proc.stderr
    assert calls == "", "a misspelled flag must not produce a check that looks like it ran"


@pytest.mark.parametrize("path", ["/sets", "/collection"])
def test_path_flag_reaches_both_sides(tmp_path, path):
    proc, calls = _run(tmp_path, GREEN, args=["--path", path])
    assert proc.returncode == 0, proc.stderr
    assert f"https://magic.dumpster.cards{path}" in calls
    assert f"https://localhost:8081{path}" in calls
