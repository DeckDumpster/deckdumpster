"""Content-addressed /static/* URLs, so an asset can actually be immutable (de-l23).

de-dai put every response behind one door and keyed the caching policy on what
the response *is*.  That left ``/static/*`` with the documents on
``public, no-cache``: correct, because a URL whose bytes can change under a
client can only ever revalidate, but it costs a conditional round trip per
subresource per page load, and the collection page names nine of them.

WHAT MAKES A URL IMMUTABLE IS THE URL.  ``/static/shared.<digest>.css`` names
one exact byte string: change the file and the digest changes, so the page that
references it references a *different* URL on the next load.  Nothing the client
holds is ever wrong, which is what earns the year that ``CACHE_IMMUTABLE``'s
docstring says a hash would earn.

THE DIGEST GOES IN THE FILENAME, NEVER IN A DIRECTORY.  ``vendor/keyrune/
keyrune.min.css`` asks for ``url('fonts/keyrune.woff2')``, and a relative URL
resolves against the directory: hashing the path segment above it would send
every glyph request somewhere that does not exist -- the exact 404 that
``tests/test_vendored_fonts.py`` exists to prevent, arrived at from the other
side.  ``keyrune.min.<digest>.css`` sits in the same directory it always did.

HTML IS NEVER CONTENT-ADDRESSED.  A document is rewritten on the way out (see
:meth:`AssetHasher.rewrite`), so its bytes on the wire change whenever any asset
it names changes while its own file on disk does not.  A digest taken from the
file would be a promise about bytes nobody sent.  Documents stay on
``CACHE_DOCUMENT``, which is where de-dai put them and where they belong: the
document is the thing that has to be re-fetched for a deploy to be visible at
all.
"""

import hashlib
import re
import threading
from dataclasses import dataclass
from pathlib import Path

#: Hex characters of SHA-256 kept in a URL.  64 bits: a collision means serving
#: one asset's bytes under another's URL, and at this population that is not a
#: risk anyone will ever meet.
DIGEST_LENGTH = 16

#: What may carry a digest -- every type this server serves except HTML.  See
#: the module docstring for why HTML is excluded, and note that the exclusion is
#: what makes a hashed URL safe to answer with the file's own bytes: everything
#: in here is served exactly as it sits on disk.
HASHABLE_SUFFIXES = frozenset({
    ".css", ".js", ".svg", ".ico", ".jpeg", ".jpg", ".png", ".webp",
    ".woff2", ".woff", ".ttf", ".eot",
})

#: ``shared.0123456789abcdef.css`` -> stem ``shared``, digest, suffix ``css``.
#: The digest class is fixed-width hex, which no filename in this tree wears:
#: ``chart.umd.min.js`` splits into components that are none of them 16 hex
#: characters, so a real name can never be read as a hashed one.
_HASHED = re.compile(r"^(?P<stem>.+)\.(?P<digest>[0-9a-f]{%d})\.(?P<suffix>[^.]+)$"
                     % DIGEST_LENGTH)

#: A literal ``/static/...`` reference in a document.  The character class stops
#: at the quote, the ``?`` and the ``#`` that end a URL in markup or in a JS
#: string, so the match is exactly the path.
_REFERENCE = re.compile(rb"/static/([A-Za-z0-9_./-]+)")


@dataclass(frozen=True)
class ResolvedAsset:
    """A ``/static/`` request that names a file, and what it may promise."""

    path: Path
    #: True only when the URL carried the digest of the bytes about to be sent.
    content_addressed: bool


class AssetHasher:
    """Digests for one static directory, plus the two translations that use them.

    One instance per directory per process (see :func:`hasher_for`) -- the
    handler is constructed per request, so a per-handler cache would hash every
    asset on every page load.
    """

    def __init__(self, static_dir: Path):
        self.static_dir = static_dir.resolve()
        # rel -> (mtime_ns, size, digest).  Concurrent misses may hash the same
        # file twice; they compute the same value, and dict assignment is
        # atomic, so the only cost is the duplicated read.
        self._digests: dict[str, tuple[int, int, str]] = {}
        # rel -> the contained absolute path, for names that turned out to be
        # files.  A document names its assets a dozen times over and every
        # `Path.resolve` is a walk of syscalls; see `_within`.
        self._paths: dict[str, Path] = {}

    # ── digests ─────────────────────────────────────────────────────────────

    def digest(self, rel: str) -> str | None:
        """The digest of the bytes ``rel`` holds *now*, or None if it holds none.

        Re-stat'ed on every call, and re-read whenever mtime or size moved.  The
        digest is still taken from the content -- mtime only decides whether the
        cached one may be reused, which keeps "this URL describes what is on
        disk" true after an edit with no restart.  That property is what lets
        :meth:`resolve` answer a digest it does not recognise with a 404 instead
        of quietly serving different bytes.
        """
        path = self._within(rel)
        if path is None or path.suffix not in HASHABLE_SUFFIXES:
            return None
        try:
            stat = path.stat()
        except OSError:
            return None
        cached = self._digests.get(rel)
        if cached is not None and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
            return cached[2]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:DIGEST_LENGTH]
        self._digests[rel] = (stat.st_mtime_ns, stat.st_size, digest)
        return digest

    def hashed_url(self, rel: str) -> str | None:
        """``shared.css`` -> ``/static/shared.<digest>.css``, or None if not hashable."""
        digest = self.digest(rel)
        if digest is None:
            return None
        base, _, suffix = rel.rpartition(".")
        return f"/static/{base}.{digest}.{suffix}"

    # ── the two translations ────────────────────────────────────────────────

    def rewrite(self, document: bytes) -> bytes:
        """Point every ``/static/`` reference in a document at its hashed URL.

        The pages keep naming their assets by the path a person can find on
        disk; the digest is minted here, at the moment the document goes out, so
        there is no build step to run and nothing to regenerate after an edit.

        A reference that names no file, or names one that may not be hashed, is
        left exactly as written.  It then takes ``CACHE_DOCUMENT`` when it is
        requested, which is today's behaviour -- an asset opts *in* to immutable
        by existing, and a typo in a template stays the visible 404 it is.
        """
        def replace(match: re.Match[bytes]) -> bytes:
            rel = match.group(1).decode("utf-8", "replace")
            hashed = self.hashed_url(rel)
            return match.group(0) if hashed is None else hashed.encode("utf-8")

        return _REFERENCE.sub(replace, document)

    def resolve(self, rel: str) -> ResolvedAsset | None:
        """Map a requested ``/static/`` path to the file that answers it.

        Three outcomes, and no fourth:

        * the path names a file -> that file, *not* content-addressed.  Every
          URL that worked before this change still works and still revalidates.
        * the path is a hashed URL whose digest matches -> the underlying file,
          content-addressed, and the caller may promise a year.
        * anything else, including a hashed URL whose digest is stale -> None,
          which the caller turns into the same 404 any unknown asset gets.

        The stale case is the load-bearing one.  Serving current bytes under a
        URL that asked for older ones is how a client ends up holding the wrong
        thing under an ``immutable`` promise it cannot revalidate away; the
        window for it is a page whose HTML the client fetched before the deploy,
        and that HTML is ``no-cache``, so the correct answer costs one 404 and
        the next load has the right URL.
        """
        direct = self._within(rel)
        if direct is None:
            return None
        if direct.is_file():
            return ResolvedAsset(direct, content_addressed=False)

        match = _HASHED.match(direct.name)
        if match is None:
            return None
        base_rel = f"{rel[:-len(direct.name)]}{match['stem']}.{match['suffix']}"
        base = self._within(base_rel)
        if base is None or not base.is_file():
            return None
        if self.digest(base_rel) != match["digest"]:
            return None
        return ResolvedAsset(base, content_addressed=True)

    # ── containment ─────────────────────────────────────────────────────────

    def _within(self, rel: str) -> Path | None:
        """``static_dir / rel``, or None if that escapes the static directory.

        Two checks, because they answer different questions.  The lexical one
        rejects what a request can carry -- an absolute path (which ``/`` on the
        right of a join silently *replaces* the left with) and any ``..`` -- and
        costs nothing, so a hostile path never reaches the filesystem.  The
        resolved one then answers the question only the filesystem can, which is
        whether a symlink in the tree points out of it.

        The resolved answer is memoized, and only for names that turned out to
        be files: a document names a dozen assets and each rewrite would
        otherwise re-walk every one of them (measured 254 us per `resolve` on
        the deploy box's filesystem, 5 ms of syscalls per page render).  Keying
        the memo on "is a file" is what bounds it to the tree on disk rather
        than to whatever paths a client cares to invent.
        """
        if rel.startswith("/") or "\0" in rel or ".." in rel.split("/"):
            return None
        cached = self._paths.get(rel)
        if cached is not None:
            return cached
        candidate = (self.static_dir / rel).resolve()
        if not candidate.is_relative_to(self.static_dir):
            return None
        if candidate.is_file():
            self._paths[rel] = candidate
        return candidate


_HASHERS: dict[Path, AssetHasher] = {}
_HASHERS_LOCK = threading.Lock()


def hasher_for(static_dir: Path) -> AssetHasher:
    """The process-wide hasher for ``static_dir``, made on first use."""
    key = Path(static_dir).resolve()
    with _HASHERS_LOCK:
        hasher = _HASHERS.get(key)
        if hasher is None:
            hasher = AssetHasher(key)
            _HASHERS[key] = hasher
        return hasher
