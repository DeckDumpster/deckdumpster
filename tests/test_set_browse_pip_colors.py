"""Set-browse finish pips are coloured by finish rank, not by rarity (sp-6v0bhz).

Rank 0 nonfoil slate, rank 1 foil blue, rank 2 etched violet -- dumpstar's
progression. Unowned is an outline in the colour; owned is filled with it.

To run: uv run pytest tests/test_set_browse_pip_colors.py -v
"""

import json

import pytest

from tests import test_set_browse_tile_number as base
from tests.test_set_browse_tile_number import browser, load  # noqa: F401  (fixtures)

SLATE = "rgb(111, 120, 151)"
BLUE = "rgb(120, 200, 240)"
VIOLET = "rgb(166, 74, 201)"
COLOR = {"nonfoil": SLATE, "foil": BLUE, "etched": VIOLET}
ALL = ["nonfoil", "foil", "etched"]


def _card(pid, rarity, owned):
    row = base._row(pid, pid, ALL)
    row["rarity"] = rarity
    row["owned"] = [{"finish": f, "qty": 1 if f in owned else 0} for f in ALL]
    row["qty"] = len(owned)
    return row


@pytest.fixture(autouse=True)
def rows():
    saved = base._PAYLOAD
    rows = [
        _card("unowned", "rare", []),
        _card("common", "common", ALL),
        _card("mythic", "mythic", ["nonfoil"]),
    ]
    base._PAYLOAD = {**saved, "rows": rows, "total": len(rows)}
    yield
    base._PAYLOAD = saved


def _style(page, pid, finish, prop):
    return page.locator(
        f'.sheet-card[data-printing-id="{pid}"] .finish-pip[data-finish="{finish}"]'
    ).evaluate(f"e => getComputedStyle(e).{prop}")


@pytest.mark.parametrize("finish", ALL)
def test_an_unowned_pip_is_an_outline_in_its_finish_colour(load, finish):
    page = load(1280)
    assert _style(page, "unowned", finish, "borderTopColor") == COLOR[finish]
    assert _style(page, "unowned", finish, "backgroundColor") == "rgba(0, 0, 0, 0)"


@pytest.mark.parametrize("finish", ALL)
def test_an_owned_common_pip_fills_with_its_finish_colour(load, finish):
    page = load(1280)
    assert _style(page, "common", finish, "backgroundColor") == COLOR[finish]


def test_an_owned_mythic_nonfoil_pip_ignores_rarity(load):
    page = load(1280)
    assert _style(page, "mythic", "nonfoil", "backgroundColor") == SLATE
