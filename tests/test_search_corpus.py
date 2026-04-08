"""Tier 1: Parameterized tests against the curated query corpus."""

import pathlib

import pytest
import yaml

from mtg_collector.search import SearchError, compile_query, parse_query
from mtg_collector.search.compiler import execute_search

# Load corpus
_CORPUS_PATH = pathlib.Path(__file__).parent / "fixtures" / "search_query_corpus.yaml"
with open(_CORPUS_PATH) as f:
    _CORPUS = yaml.safe_load(f)

_SHOULD_PARSE = [e for e in _CORPUS if e["should_parse"]]
_SHOULD_ERROR = [e for e in _CORPUS if not e["should_parse"]]
_COMPILER_SUPPORTED = [e for e in _CORPUS if e["compiler_supported"]]


def _qid(entry):
    return entry["query"] or "<empty>"


class TestCorpusParsing:
    """All should_parse=true entries must parse without error."""

    @pytest.mark.parametrize("entry", _SHOULD_PARSE, ids=[_qid(e) for e in _SHOULD_PARSE])
    def test_parses_successfully(self, entry):
        ast = parse_query(entry["query"])
        assert ast is not None

    @pytest.mark.parametrize("entry", _SHOULD_ERROR, ids=[_qid(e) for e in _SHOULD_ERROR])
    def test_raises_search_error(self, entry):
        with pytest.raises(SearchError):
            parse_query(entry["query"])


class TestCorpusCompilation:
    """All compiler_supported=true entries must compile and execute."""

    @pytest.mark.parametrize(
        "entry", _COMPILER_SUPPORTED, ids=[_qid(e) for e in _COMPILER_SUPPORTED]
    )
    def test_compiles_to_sql(self, entry):
        ast = parse_query(entry["query"])
        compiled = compile_query(ast)
        assert compiled.where_sql
        # Should not contain unsupported fallback for supported queries
        assert "1=0" not in compiled.where_sql, (
            f"Unsupported keyword fallback in: {entry['query']}"
        )

    @pytest.mark.parametrize(
        "entry", _COMPILER_SUPPORTED, ids=[_qid(e) for e in _COMPILER_SUPPORTED]
    )
    def test_executes_against_fixture(self, search_db, entry):
        ast = parse_query(entry["query"])
        compiled = compile_query(ast)
        mode = "collection" if entry.get("category") == "collection" else "all"
        rows, timings = execute_search(search_db, compiled, mode=mode)
        assert isinstance(rows, list)
        assert "query_ms" in timings
