"""A vendored font file has to be the one its own stylesheet asks for.

Tier 1 — no container, no network.

The icon fonts are served by the app out of `static/vendor/<name>/`, so a
`url()` in a vendored stylesheet is a promise about a path under that
directory. Nothing enforced it: `keyrune.min.css` shipped with upstream's
`url('../fonts/…')`, written for upstream's sibling `css/` + `fonts/` layout,
while the vendoring flattened the stylesheet in beside `fonts/`. Every request
went to `/static/vendor/fonts/keyrune.woff2` and 404'd, so `<i class="ss
ss-fin">` rendered as blank space on card_detail, deck_builder, recent and
disambiguate. `.ss` has no fallback family, so there was nothing to see and
nothing to log — the glyph is simply not there, which reads as "this set has
no icon". `mana-font/mana.min.css` in the same tree had its relative path
right, which is why only one of the two broke.

The invariant asserted is that every font file vendored under a stylesheet's
`fonts/` directory is reachable from that stylesheet — not that every `url()`
resolves. `mana.min.css` also declares an MPlantin face whose files were
deliberately not vendored; nothing in this app uses the `.card-text` classes
that call for it, and that face carries a full serif fallback stack, so its
absence costs nothing. A file we did vendor and cannot reach is the bug.
"""

import re
from pathlib import Path

import pytest

from mtg_collector.cli import crack_pack_server as cps

VENDOR = Path(cps.__file__).resolve().parent.parent / "static" / "vendor"

#: url(...) in a stylesheet, minus any ?version and #fragment.
_URL = re.compile(r"""url\(\s*['"]?([^'")?#]+)""")


def _stylesheets():
    return sorted(p for p in VENDOR.glob("*/*.css") if (p.parent / "fonts").is_dir())


def test_there_are_vendored_font_stylesheets_to_check():
    """A glob that silently matched nothing would pass the test below."""
    assert _stylesheets(), f"no vendored font stylesheets under {VENDOR}"


@pytest.mark.parametrize("css", _stylesheets(), ids=lambda p: p.parent.name)
def test_every_vendored_font_file_is_reachable_from_its_stylesheet(css):
    reachable = {
        (css.parent / ref).resolve()
        for ref in _URL.findall(css.read_text(encoding="utf-8-sig"))
    }
    vendored = sorted(p for p in (css.parent / "fonts").iterdir() if p.is_file())
    assert vendored, f"{css.parent.name}/fonts/ is empty"

    unreachable = [p.name for p in vendored if p.resolve() not in reachable]
    assert not unreachable, (
        f"{css.name} does not resolve to the font files vendored beside it: "
        f"{unreachable}. The glyphs go blank and nothing else complains."
    )
