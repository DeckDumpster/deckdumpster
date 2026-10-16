"""The favicon is the header's brand mark, derived from it so they cannot drift."""
import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "mtg_collector" / "static"

_spec = importlib.util.spec_from_file_location("build_favicons", ROOT / "scripts" / "build_favicons.py")
build_favicons = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_favicons)

ICON_LINKS = [
    '<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">',
    '<link rel="icon" href="/static/favicon-32.png" type="image/png" sizes="32x32">',
    '<link rel="apple-touch-icon" href="/static/apple-touch-icon.png" sizes="180x180">',
]


def _rects(text):
    return [sorted(re.findall(r'([\w-]+)="([^"]*)"', m)) for m in re.findall(r"<rect ([^>]*?)/>", text)]


def test_favicon_svg_has_the_headers_shapes():
    header = re.search(r'<a href="/" class="brand-logo".*?</a>', (STATIC / "collection.html").read_text(), re.S).group(0)
    favicon = (STATIC / "favicon.svg").read_text()
    assert len(_rects(header)) == 2
    assert _rects(favicon) == _rects(header)
    for attr in ('viewBox="0 0 32 32"', 'stroke-width="2.2"'):
        assert attr in header and attr in favicon


def test_rasters_are_generated_from_the_svg():
    built = build_favicons.build((STATIC / "favicon.svg").read_text())
    for name, data in built.items():
        assert (STATIC / name).read_bytes() == data, f"{name} is stale: run scripts/build_favicons.py"


def test_apple_touch_icon_is_180_square():
    data = (STATIC / "apple-touch-icon.png").read_bytes()
    assert data[16:24] == (180).to_bytes(4, "big") * 2


def test_every_page_links_every_icon():
    pages = sorted(STATIC.glob("*.html"))
    assert pages
    for page in pages:
        text = page.read_text()
        for link in ICON_LINKS:
            assert link in text, f"{page.name} lacks {link}"
        assert "favicon.ico" not in text
