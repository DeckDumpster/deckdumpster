"""HTTP response semantics: cache policy, validators, encoding, ranges (de-dai).

Everything the server sends leaves through one function, and that function
decides the caching rules from what the response *is* rather than from a string
the caller remembered to pass.  The functions here are the decisions; they take
headers and bytes and return values, so the whole policy is testable without a
socket.

WHY THIS EXISTS.  Every HTML page was served ``public, max-age=86400`` with no
validator.  magic.dumpster.cards reaches this process through a Cloudflare
tunnel, so the edge held each document for a day with nothing to revalidate
against: six deploys landed one evening and the public site showed none of them,
while the same container on the LAN showed all six.  A hard refresh does not
help -- it defeats the browser cache, not the edge.

THE POLICY IS KEYED ON THE RESPONSE, NOT THE CALLER.  A URL whose bytes can
change under a client can only ever revalidate; ``immutable`` is a promise about
the URL, and making it about anything else is how a deploy goes invisible.
"""

import hashlib
import re

#: Documents and every non-content-addressed asset.  ``no-cache`` does not mean
#: "do not store" -- it means "store, but revalidate before reuse", which is
#: exactly the behaviour a deploy needs: the edge keeps its copy and a matching
#: ETag turns the next request into a 304 instead of a transfer.
#:
#: A /static/* URL with no digest in it is here for that reason: its bytes can
#: change under a client, so a stale style sheet would outlive a deploy exactly
#: the way a stale page did.  A digest (see CACHE_HASHED_ASSET) is how an asset
#: stops paying the conditional round trip that buys.
CACHE_DOCUMENT = "public, no-cache"

#: A content-addressed asset: /static/shared.<digest>.css (de-l23).  The digest
#: is of the bytes, so this URL means these bytes and can mean nothing else --
#: change the file and every page names a different URL on its next load, which
#: is itself no-cache and so is re-fetched.  Nothing a client holds can be
#: wrong, so there is nothing for it to ask about: a year, and no conditional
#: round trip per subresource per page load.
#:
#: This is the promise CACHE_IMMUTABLE's docstring says a hash in the URL would
#: earn, and mtg_collector/static_assets.py is what puts one there.  The two are
#: separate constants because the ingest path still has no digest, only a
#: convention, and a convention is worth a day.
CACHE_HASHED_ASSET = "public, max-age=31536000, immutable"

#: The ingest-image path, and nothing else.  Its value is EXACTLY what that path
#: already served: this is the one place that was doing caching correctly and it
#: is not being changed, only moved behind the same door as everything else.
#:
#: Read the day as the ceiling on how wrong `immutable` can go here, because
#: nothing about these URLs makes them content-addressed.  What they have is a
#: convention -- `_api_ingest_upload2` refuses a name that already exists rather
#: than overwriting it, and the corner path timestamps to the second -- and a
#: convention has edges: a delete frees a name for re-upload, and two corner
#: uploads inside one second collide.  A hash in the URL is what would earn a
#: year.  Do not raise this without putting one there first -- CACHE_HASHED_ASSET
#: is what that looks like once one is there, and it is a different constant
#: precisely because these URLs still have none.
CACHE_IMMUTABLE = "public, max-age=86400, immutable"

#: ``private`` keeps collection data out of the shared edge cache; ``no-cache``
#: keeps the validator useful, so a repeated identical query costs a 304 rather
#: than a multi-megabyte body.  The previous behaviour was no Cache-Control at
#: all, which is not the same as "not cached": a heuristic cache is free to
#: invent a lifetime, and a day-old catalogue served from one is indistinguish-
#: able from an ingest bug.
CACHE_API = "private, no-cache"

#: Compressible content types.  Images, PDFs and fonts in already-compressed
#: containers are omitted: gzip costs CPU on both ends and returns nothing.
GZIPPABLE = frozenset({
    "text/html; charset=utf-8",
    "text/css",
    "text/javascript; charset=utf-8",
    "application/javascript",
    "application/json",
    "image/svg+xml",
    "font/ttf",
})

#: Below this, a gzip frame's own overhead is a meaningful share of the payload
#: and the round trip is dominated by latency anyway.
GZIP_MIN_BYTES = 1024

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def compute_etag(body: bytes, *, encoding: str | None = None) -> str:
    """Return the strong ETag for ``body`` served under ``encoding``.

    Content-derived, never mtime-derived.  "Was this page changed on disk" is
    precisely what a hash of the bytes answers, and it stays correct across a
    container rebuild, which resets every mtime without changing a byte.

    THE ETAG VARIES WITH THE ENCODING.  Identity and gzip are different
    representations of the same resource; handing both the same ETag is the
    classic way a cache serves gzipped bytes to a client that asked for none,
    or satisfies a byte range out of the wrong representation.  Two ETags plus
    ``Vary: Accept-Encoding`` makes that unrepresentable rather than unlikely.
    """
    digest = hashlib.sha256(body).hexdigest()[:32]
    suffix = f"-{encoding}" if encoding else ""
    return f'"{digest}{suffix}"'


def etag_matches(if_none_match: str | None, etag: str) -> bool:
    """Does an ``If-None-Match`` header excuse us from sending the body?

    ``*`` matches anything.  A list is compared entry by entry, and a ``W/``
    prefix is stripped from both sides: a weak comparison is what RFC 9110
    requires for If-None-Match, and we only ever mint strong tags, so the only
    weak tags in play are ones an intermediary weakened on the way out.
    """
    if not if_none_match:
        return False
    candidate = if_none_match.strip()
    if candidate == "*":
        return True
    wanted = _unweaken(etag)
    return any(_unweaken(part) == wanted for part in candidate.split(","))


def _unweaken(tag: str) -> str:
    tag = tag.strip()
    return tag[2:] if tag.startswith("W/") else tag


def negotiate_gzip(accept_encoding: str | None, content_type: str, length: int) -> bool:
    """Should this response go out gzipped?

    A substring test on the header, matching what the two call sites this
    replaces already did.  ``q=0`` refusals are not honoured, and that is a
    deliberate non-feature: no client this server serves sends one, and the
    parser to read them would be an error path with no caller.
    """
    if content_type not in GZIPPABLE or length < GZIP_MIN_BYTES:
        return False
    return "gzip" in (accept_encoding or "")


class RangeNotSatisfiable(ValueError):
    """A syntactically valid range that lies outside the representation -> 416."""


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Return the inclusive ``(start, end)`` a Range header asks for.

    ``None`` means "serve the whole thing": no header, a unit we do not speak,
    or a multi-range request.  That is not a fallback hiding an error -- RFC
    9110 requires an unsatisfiable-to-parse Range to be *ignored*, and answering
    a multipart request with the whole representation is a correct response to
    it.  Only a well-formed range that cannot land inside the representation is
    an error, and that one is a 416.
    """
    if not header:
        return None
    match = _RANGE_RE.match(header.strip())
    if not match:
        return None
    first, last = match.group(1), match.group(2)
    if not first and not last:
        return None
    if not first:
        # `bytes=-500` -- the final 500 bytes.  A suffix longer than the
        # representation is the whole representation, not an error.
        start = max(0, size - int(last))
        end = size - 1
    else:
        start = int(first)
        end = size - 1 if not last else min(int(last), size - 1)
    if size == 0 or start >= size or start > end:
        raise RangeNotSatisfiable(header)
    return start, end
