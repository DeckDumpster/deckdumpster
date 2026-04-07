"""Tests for the Scryfall-style search query parser."""

import pytest

from mtg_collector.search import (
    AndNode,
    ComparisonNode,
    ExactNameNode,
    NameSearchNode,
    NotNode,
    OrNode,
    SearchError,
    parse_query,
)


class TestBareWords:
    def test_single_word(self):
        ast = parse_query("lightning")
        assert isinstance(ast, NameSearchNode)
        assert ast.term == "lightning"

    def test_multiple_words_and(self):
        ast = parse_query("lightning bolt")
        assert isinstance(ast, AndNode)
        assert len(ast.children) == 2
        assert ast.children[0].term == "lightning"
        assert ast.children[1].term == "bolt"


class TestExactName:
    def test_quoted_exact(self):
        ast = parse_query('!"Lightning Bolt"')
        assert isinstance(ast, ExactNameNode)
        assert ast.name == "Lightning Bolt"

    def test_unquoted_exact(self):
        ast = parse_query("!bolt")
        assert isinstance(ast, ExactNameNode)
        assert ast.name == "bolt"


class TestKeywordExpressions:
    def test_colon_operator(self):
        ast = parse_query("c:r")
        assert isinstance(ast, ComparisonNode)
        assert ast.keyword == "color"
        assert ast.operator == ":"
        assert ast.value == "r"

    def test_equals_operator(self):
        ast = parse_query("c=rg")
        assert isinstance(ast, ComparisonNode)
        assert ast.operator == "="
        assert ast.value == "rg"

    def test_gte_operator(self):
        ast = parse_query("mv>=3")
        assert isinstance(ast, ComparisonNode)
        assert ast.keyword == "mana_value"
        assert ast.operator == ">="
        assert ast.value == "3"

    def test_lte_operator(self):
        ast = parse_query("pow<=5")
        assert isinstance(ast, ComparisonNode)
        assert ast.keyword == "power"
        assert ast.operator == "<="
        assert ast.value == "5"

    def test_ne_operator(self):
        ast = parse_query("c!=r")
        assert isinstance(ast, ComparisonNode)
        assert ast.operator == "!="

    def test_gt_operator(self):
        ast = parse_query("tou>3")
        assert isinstance(ast, ComparisonNode)
        assert ast.keyword == "toughness"
        assert ast.operator == ">"

    def test_lt_operator(self):
        ast = parse_query("cmc<4")
        assert isinstance(ast, ComparisonNode)
        assert ast.keyword == "mana_value"
        assert ast.operator == "<"

    def test_quoted_value(self):
        ast = parse_query('o:"enters tapped"')
        assert isinstance(ast, ComparisonNode)
        assert ast.keyword == "oracle"
        assert ast.value == "enters tapped"

    def test_type_keyword(self):
        ast = parse_query("t:creature")
        assert isinstance(ast, ComparisonNode)
        assert ast.keyword == "type"
        assert ast.value == "creature"

    def test_set_keyword(self):
        ast = parse_query("s:lea")
        assert isinstance(ast, ComparisonNode)
        assert ast.keyword == "set"
        assert ast.value == "lea"

    def test_rarity_keyword(self):
        ast = parse_query("r:rare")
        assert isinstance(ast, ComparisonNode)
        assert ast.keyword == "rarity"

    def test_format_keyword(self):
        ast = parse_query("f:modern")
        assert isinstance(ast, ComparisonNode)
        assert ast.keyword == "format"

    def test_artist_keyword(self):
        ast = parse_query("a:rush")
        assert isinstance(ast, ComparisonNode)
        assert ast.keyword == "artist"


class TestKeywordAliases:
    def test_color_aliases(self):
        for alias in ("c", "color", "colours"):
            ast = parse_query(f"{alias}:r")
            assert ast.keyword == "color", f"Failed for alias: {alias}"

    def test_type_aliases(self):
        for alias in ("t", "type"):
            ast = parse_query(f"{alias}:creature")
            assert ast.keyword == "type"

    def test_mana_value_aliases(self):
        for alias in ("mv", "cmc", "manavalue"):
            ast = parse_query(f"{alias}>=3")
            assert ast.keyword == "mana_value"

    def test_power_aliases(self):
        for alias in ("pow", "power"):
            ast = parse_query(f"{alias}>=3")
            assert ast.keyword == "power"


class TestBooleanLogic:
    def test_implicit_and(self):
        ast = parse_query("c:r t:creature")
        assert isinstance(ast, AndNode)
        assert len(ast.children) == 2

    def test_explicit_or(self):
        ast = parse_query("c:r or c:g")
        assert isinstance(ast, OrNode)
        assert len(ast.children) == 2

    def test_or_case_insensitive(self):
        ast = parse_query("c:r OR c:g")
        assert isinstance(ast, OrNode)

    def test_negation(self):
        ast = parse_query("-c:r")
        assert isinstance(ast, NotNode)
        assert isinstance(ast.child, ComparisonNode)

    def test_negation_with_and(self):
        ast = parse_query("-c:r t:creature")
        assert isinstance(ast, AndNode)
        assert isinstance(ast.children[0], NotNode)
        assert isinstance(ast.children[1], ComparisonNode)

    def test_parentheses(self):
        ast = parse_query("(c:r or c:g) t:creature")
        assert isinstance(ast, AndNode)
        assert isinstance(ast.children[0], OrNode)
        assert isinstance(ast.children[1], ComparisonNode)

    def test_nested_parens(self):
        ast = parse_query("((c:r or c:g) t:creature)")
        # Should still be valid
        assert isinstance(ast, AndNode)

    def test_negated_group(self):
        ast = parse_query("-(c:r or c:g)")
        assert isinstance(ast, NotNode)
        assert isinstance(ast.child, OrNode)


class TestComplexQueries:
    def test_full_scryfall_query(self):
        ast = parse_query('c:r t:instant mv<=2 o:"deals damage"')
        assert isinstance(ast, AndNode)
        assert len(ast.children) == 4

    def test_mixed_or_and(self):
        ast = parse_query("(c:r or c:g) t:creature pow>=4")
        assert isinstance(ast, AndNode)
        assert len(ast.children) == 3

    def test_is_flag(self):
        ast = parse_query("is:foil")
        assert isinstance(ast, ComparisonNode)
        assert ast.keyword == "is_flag"
        assert ast.value == "foil"


class TestEdgeCases:
    def test_empty_string(self):
        """Empty string should raise or return empty."""
        with pytest.raises(SearchError):
            parse_query("")

    def test_whitespace_only(self):
        with pytest.raises(SearchError):
            parse_query("   ")

    def test_unknown_keyword(self):
        with pytest.raises(SearchError) as exc_info:
            parse_query("xyz:value")
        assert "xyz" in str(exc_info.value).lower()

    def test_unknown_keyword_position(self):
        with pytest.raises(SearchError) as exc_info:
            parse_query("xyz:value")
        assert exc_info.value.position >= 0
