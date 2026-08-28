"""A page this app serves must not fetch its own stylesheets or scripts from the internet.

Tier 1 — no container, no network.

The architecture rule is that a render reads local storage and nothing else,
and a `<link>` or `<script>` pointing at a CDN breaks it in the place least
likely to be noticed: the page still works on the developer's machine. Keyrune,
mana-font, Chart.js and its date adapter are all vendored under
`static/vendor/`, and every page was repointed at them — except
`collection.html`, which kept four `cdn.jsdelivr.net` tags through the sweep and
so was the one page de-glc's font 404s could not reach. Nobody found it by
using the app; it turned up while reading the diff of an unrelated fix.

Two of those four asked for `@latest`, which jsdelivr resolves per request. The
class names behind `<i class="ss ss-XXX">` are upstream's to change, so the
collection browser's set symbols could stop matching the pinned copy every
other page draws from, with no commit here to point at.

Card images are deliberately remote (`printings.image_uri` is a Scryfall CDN
URL, injected at runtime), and an `<a href>` is a place to navigate rather than
something the page fetches. Neither is asserted on here. What is asserted is
that nothing the browser must fetch to render the page comes from another host.
"""

import re
from pathlib import Path

import pytest

from mtg_collector.cli import crack_pack_server as cps

STATIC = Path(cps.__file__).resolve().parent.parent / "static"

#: A <link href> or <script src>: what the browser fetches to render the page.
_SUBRESOURCE = re.compile(
    r"""<(?:link|script)\b[^>]*\b(?:href|src)\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE,
)

#: An absolute or protocol-relative URL — anything naming a host that is not us.
_EXTERNAL = re.compile(r"""^(?:[a-z][a-z0-9+.-]*:)?//""", re.IGNORECASE)


def _pages():
    return sorted(STATIC.glob("*.html"))


def test_there_are_pages_to_check():
    """A glob that silently matched nothing would pass the test below."""
    assert _pages(), f"no pages under {STATIC}"


@pytest.mark.parametrize("page", _pages(), ids=lambda p: p.name)
def test_no_page_loads_a_stylesheet_or_script_from_another_host(page):
    external = [
        url
        for url in _SUBRESOURCE.findall(page.read_text(encoding="utf-8-sig"))
        if _EXTERNAL.match(url.strip())
    ]
    assert not external, (
        f"{page.name} fetches {external} from the internet to render. Vendor it "
        f"under static/vendor/ and point at /static/vendor/... instead."
    )
