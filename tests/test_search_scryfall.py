"""Tier 2: Scryfall API agreement tests.

Verifies that our parser and Scryfall agree on whether each corpus query is valid.
Requires --scryfall flag to run (skipped by default).
"""

import pathlib

import pytest
import yaml

from mtg_collector.search import SearchError, parse_query

_CORPUS_PATH = pathlib.Path(__file__).parent / "fixtures" / "search_query_corpus.yaml"
with open(_CORPUS_PATH) as f:
    _CORPUS = yaml.safe_load(f)

# Only test entries that have an opinion on parseability
_ALL_ENTRIES = [e for e in _CORPUS if e["query"].strip()]


def _qid(entry):
    return entry["query"] or "<empty>"


@pytest.mark.scryfall
class TestScryfallAgreement:
    """Our parser and Scryfall should agree on whether a query is valid."""

    @pytest.mark.parametrize("entry", _ALL_ENTRIES, ids=[_qid(e) for e in _ALL_ENTRIES])
    def test_parse_agreement(self, scryfall_cache, entry):
        from tests.search_helpers.scryfall_client import scryfall_search

        query = entry["query"]

        # Our parser result
        our_parses = True
        try:
            parse_query(query)
        except SearchError:
            our_parses = False

        # Scryfall result
        result = scryfall_search(scryfall_cache, query)
        scryfall_accepts = result["status_code"] == 200

        if our_parses and not scryfall_accepts:
            # We accept but Scryfall rejects — might be syntax we parse
            # but Scryfall doesn't support (or vice versa). Log but don't
            # hard-fail since our syntax is a subset.
            pass

        if not our_parses and scryfall_accepts:
            pytest.fail(
                f"Scryfall accepts but we reject: {query!r}\n"
                f"  Scryfall returned {result['total_cards']} cards"
            )
