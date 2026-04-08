"""Tests for the Scryfall search SQL compiler."""

import sqlite3

import pytest

from mtg_collector.search import compile_query, parse_query
from mtg_collector.search.compiler import CompiledQuery


def _compile(q: str) -> CompiledQuery:
    """Helper: parse and compile a query string."""
    return compile_query(parse_query(q))


class TestColorCompilation:
    def test_color_contains(self):
        c = _compile("c:r")
        assert "colors LIKE" in c.where_sql
        assert '%"R"%' in c.params

    def test_color_exact(self):
        c = _compile("c=rg")
        assert "json_array_length" in c.where_sql
        assert '%"R"%' in c.params
        assert '%"G"%' in c.params

    def test_color_superset(self):
        c = _compile("c>=uw")
        assert '%"W"%' in c.params
        assert '%"U"%' in c.params

    def test_color_subset(self):
        c = _compile("c<=rg")
        assert "NOT LIKE" in c.where_sql
        # Params should include the excluded colors (W, U, B)
        assert any('"W"' in str(p) or '"U"' in str(p) or '"B"' in str(p) for p in c.params)

    def test_colorless(self):
        c = _compile("c:c")
        assert "IS NULL" in c.where_sql or "'[]'" in c.where_sql

    def test_multicolor(self):
        c = _compile("c:m")
        assert "json_array_length" in c.where_sql

    def test_guild_name(self):
        c = _compile("c:azorius")
        assert '%"W"%' in c.params
        assert '%"U"%' in c.params

    def test_color_identity(self):
        c = _compile("id:rg")
        assert "color_identity" in c.where_sql

    def test_color_numeric(self):
        c = _compile("c=2")
        assert "json_array_length" in c.where_sql


class TestNumericCompilation:
    def test_cmc_gte(self):
        c = _compile("mv>=3")
        assert "card.cmc" in c.where_sql
        assert 3.0 in c.params

    def test_cmc_exact(self):
        c = _compile("cmc=5")
        assert 5.0 in c.params

    def test_power_gt(self):
        c = _compile("pow>5")
        assert "power" in c.where_sql.lower()
        assert 5.0 in c.params

    def test_toughness_lte(self):
        c = _compile("tou<=3")
        assert "toughness" in c.where_sql.lower()

    def test_power_star(self):
        c = _compile("pow:*")
        assert "'*'" in c.where_sql


class TestTextCompilation:
    def test_name_search(self):
        c = _compile("bolt")
        assert "card.name LIKE" in c.where_sql
        assert "p.flavor_name LIKE" in c.where_sql
        assert "type_line" not in c.where_sql  # type line requires t: prefix
        assert "oracle_text" not in c.where_sql  # oracle text requires o: prefix
        assert "%bolt%" in c.params

    def test_oracle_text(self):
        c = _compile('o:"enters tapped"')
        assert "oracle_text" in c.where_sql.lower()
        assert "%enters tapped%" in c.params

    def test_type_like(self):
        c = _compile("t:creature")
        assert "type_line" in c.where_sql.lower()

    def test_flavor_text(self):
        c = _compile("ft:fire")
        assert "flavor_text" in c.where_sql

    def test_artist(self):
        c = _compile("a:rush")
        assert "artist" in c.where_sql.lower()

    def test_exact_name(self):
        c = _compile('!"Lightning Bolt"')
        assert "oracle_id" in c.where_sql
        assert "Lightning Bolt" in c.params


class TestRarityCompilation:
    def test_rarity_exact(self):
        c = _compile("r:rare")
        assert "p.rarity = ?" in c.where_sql
        assert "rare" in c.params

    def test_rarity_alias(self):
        c = _compile("r:r")
        assert "rare" in c.params

    def test_rarity_gte(self):
        c = _compile("r>=r")
        assert "CASE" in c.where_sql
        assert 2 in c.params  # rare = ordinal 2


class TestFormatCompilation:
    def test_format_legal(self):
        c = _compile("f:standard")
        assert "json_extract" in c.where_sql
        assert "standard" in c.params

    def test_banned(self):
        c = _compile("banned:modern")
        assert "banned" in c.where_sql
        assert "modern" in c.params

    def test_restricted(self):
        c = _compile("restricted:vintage")
        assert "restricted" in c.where_sql


class TestSetCompilation:
    def test_set_exact(self):
        c = _compile("s:lea")
        assert "set_code" in c.where_sql
        assert "lea" in c.params


class TestFlagCompilation:
    def test_is_foil(self):
        c = _compile("is:foil")
        assert "finishes" in c.where_sql

    def test_is_fullart(self):
        c = _compile("is:fullart")
        assert "full_art" in c.where_sql

    def test_is_reserved(self):
        c = _compile("is:reserved")
        assert "reserved" in c.where_sql

    def test_is_promo(self):
        c = _compile("is:promo")
        assert "promo" in c.where_sql


class TestBooleanCompilation:
    def test_and(self):
        c = _compile("c:r t:creature")
        assert " AND " in c.where_sql

    def test_or(self):
        c = _compile("c:r or c:g")
        assert " OR " in c.where_sql

    def test_not(self):
        c = _compile("-c:r")
        assert "NOT" in c.where_sql


class TestDisplayModifiers:
    def test_order_extracted(self):
        c = _compile("c:r order:cmc")
        assert c.order_by == "cmc"
        # order: should not appear in WHERE
        assert "order" not in c.where_sql.lower()

    def test_direction_extracted(self):
        c = _compile("c:r direction:desc")
        assert c.order_dir == "desc"


class TestKeywordAbilities:
    def test_keyword_search(self):
        c = _compile("kw:flying")
        assert "keywords" in c.where_sql.lower()


class TestCollectionKeywords:
    """Test compilation of collection-specific keywords."""

    def test_status_owned(self):
        c = _compile("status:owned")
        assert "c.status = ?" in c.where_sql
        assert "owned" in c.params
        assert c.has_status_filter

    def test_status_ordered(self):
        c = _compile("status:ordered")
        assert "c.status = ?" in c.where_sql
        assert "ordered" in c.params

    def test_status_not_equal(self):
        c = _compile("status!=sold")
        assert "c.status != ?" in c.where_sql
        assert "sold" in c.params

    def test_status_unknown(self):
        c = _compile("status:bogus")
        assert "1=0" in c.where_sql

    def test_added_gte(self):
        c = _compile("added>=2024-01-01")
        assert "acquired_at" in c.where_sql
        assert "2024-01-01" in c.params

    def test_added_lte(self):
        c = _compile("added<=2025-12-31")
        assert "acquired_at" in c.where_sql

    def test_price_gte(self):
        c = _compile("price>=5.00")
        assert c.needs_price_join
        assert "_lp.price" in c.where_sql
        assert 5.0 in c.params

    def test_deck_wildcard(self):
        c = _compile("deck:*")
        assert c.needs_deck_join
        assert "deck_id IS NOT NULL" in c.where_sql

    def test_deck_wildcard_negated(self):
        c = _compile("deck!=*")
        assert c.needs_deck_join
        assert "deck_id IS NULL" in c.where_sql

    def test_deck_named(self):
        c = _compile('deck:"Mono Red"')
        assert c.needs_deck_join
        assert "d.name" in c.where_sql

    def test_binder_wildcard(self):
        c = _compile("binder:*")
        assert "binder_id IS NOT NULL" in c.where_sql

    def test_binder_named(self):
        c = _compile('binder:"Trade"')
        assert "b.name" in c.where_sql

    def test_is_unassigned(self):
        c = _compile("is:unassigned")
        assert c.needs_deck_join
        assert "deck_id IS NULL" in c.where_sql
        assert "binder_id IS NULL" in c.where_sql

    def test_is_decked(self):
        c = _compile("is:decked")
        assert c.needs_deck_join
        assert "deck_id IS NOT NULL" in c.where_sql

    def test_is_bindered(self):
        c = _compile("is:bindered")
        assert "binder_id IS NOT NULL" in c.where_sql

    def test_is_wanted(self):
        c = _compile("is:wanted")
        assert c.needs_wishlist_join
        assert "_wl.id IS NOT NULL" in c.where_sql

    def test_not_wanted(self):
        c = _compile("not:wanted")
        assert c.needs_wishlist_join
        assert "NOT" in c.where_sql
        assert "_wl.id IS NOT NULL" in c.where_sql


class TestSQLValidity:
    """Test that compiled queries produce valid SQL by executing against an in-memory DB."""

    @pytest.fixture
    def db(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        from mtg_collector.db.schema import init_db
        init_db(conn)
        # Insert test data
        conn.execute("""
            INSERT INTO cards (oracle_id, name, type_line, mana_cost, cmc, oracle_text,
                colors, color_identity, keywords, legalities)
            VALUES ('t1', 'Test Card', 'Creature - Human', '{R}', 1.0, 'Test text.',
                '["R"]', '["R"]', '["Haste"]',
                '{"standard":"legal","modern":"legal"}')
        """)
        conn.execute("""
            INSERT INTO sets (set_code, set_name, set_type, released_at, digital)
            VALUES ('tst', 'Test Set', 'expansion', '2024-01-01', 0)
        """)
        conn.execute("""
            INSERT INTO printings (printing_id, oracle_id, set_code, collector_number,
                rarity, frame_effects, border_color, full_art, promo, promo_types,
                finishes, artist, power, toughness, layout, digital, reserved, reprint, games)
            VALUES ('p1', 't1', 'tst', '1', 'rare', '[]', 'black', 0, 0, '[]',
                '["nonfoil"]', 'Test Artist', '2', '1', 'normal', 0, 0, 0, '["paper"]')
        """)
        conn.execute("""
            INSERT INTO collection (printing_id, finish, condition, language, acquired_at, source, status)
            VALUES ('p1', 'nonfoil', 'Near Mint', 'English', '2024-01-01', 'manual', 'owned')
        """)
        conn.execute("""
            INSERT INTO decks (name, created_at, updated_at)
            VALUES ('Test Deck', '2024-01-01', '2024-01-01')
        """)
        conn.execute("""
            INSERT INTO binders (name, created_at, updated_at)
            VALUES ('Test Binder', '2024-01-01', '2024-01-01')
        """)
        conn.execute("INSERT INTO cards_fts(cards_fts) VALUES('rebuild')")
        conn.commit()
        yield conn
        conn.close()

    @pytest.mark.parametrize("query", [
        "test",
        "c:r",
        "c:r t:creature",
        "mv<=1",
        "r:rare",
        "r>=r",
        "f:modern",
        "s:tst",
        "a:artist",
        "is:nonfoil",
        "pow>=2",
        "tou<=1",
        "kw:haste",
        "(c:r or c:g) t:creature",
        "-c:b",
        '!"Test Card"',
        'o:"Test text"',
        "c:r order:cmc direction:desc",
        # Collection-specific queries
        "status:owned",
        "status:ordered",
        "added>=2024-01-01",
        "deck:*",
        "deck!=*",
        'deck:"Test Deck"',
        "binder:*",
        'binder:"Test Binder"',
        "is:unassigned",
        "is:decked",
        "is:bindered",
        "is:wanted",
        "not:wanted",
        "status:owned c:r t:creature",
        "is:unassigned added>=2024-01-01",
        "order:added direction:desc",
    ])
    def test_valid_sql(self, db, query):
        """Every supported query should produce valid SQL that executes without error."""
        from mtg_collector.search.compiler import execute_search
        compiled = compile_query(parse_query(query))
        rows, timings = execute_search(db, compiled, mode="collection")
        assert isinstance(rows, list)
        assert "query_ms" in timings
