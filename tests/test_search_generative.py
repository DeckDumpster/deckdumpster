"""Tier 3: Generative testing with the reverse parser.

Local tests (always run): verify generated queries parse, compile, and execute.
Scryfall tests (--scryfall): compare results with Scryfall API (report mode).
Collection tests: verify collection-specific keywords parse/compile/execute.
"""

import json
import pathlib
import random

import pytest

from mtg_collector.search import SearchError, compile_query, parse_query
from mtg_collector.search.compiler import execute_search


@pytest.mark.generative
class TestGenerativeLocal:
    """Generate queries from seeds, verify they parse/compile/execute locally."""

    def test_all_parse(self, seed_range):
        """Every generated query must parse without error."""
        from tests.search_helpers.query_generator import QueryGenerator

        for seed in seed_range:
            rng = random.Random(seed)
            gen = QueryGenerator(rng, supported_only=True)
            query, _ = gen.generate()
            try:
                ast = parse_query(query)
                assert ast is not None
            except SearchError as e:
                pytest.fail(f"Seed {seed} generated unparseable query: {query!r}\n  Error: {e}")

    def test_all_compile(self, seed_range):
        """Every generated query must compile to valid SQL (no unsupported fallback)."""
        from tests.search_helpers.query_generator import QueryGenerator

        for seed in seed_range:
            rng = random.Random(seed)
            gen = QueryGenerator(rng, supported_only=True)
            query, _ = gen.generate()
            ast = parse_query(query)
            compiled = compile_query(ast)
            assert "1=0" not in compiled.where_sql, (
                f"Seed {seed}: unsupported keyword in {query!r}"
            )

    def test_all_execute(self, search_db, seed_range):
        """Every generated query must execute without SQL errors."""
        from tests.search_helpers.query_generator import QueryGenerator

        for seed in seed_range:
            rng = random.Random(seed)
            gen = QueryGenerator(rng, supported_only=True)
            query, _ = gen.generate()
            ast = parse_query(query)
            compiled = compile_query(ast)
            try:
                rows, _ = execute_search(search_db, compiled, mode="all")
                assert isinstance(rows, list)
            except Exception as e:
                pytest.fail(f"Seed {seed}: SQL error for {query!r}\n  Error: {e}")


@pytest.mark.generative
class TestGenerativeCollection:
    """Generate queries with collection-specific keywords, verify locally."""

    def test_collection_parse(self, seed_range):
        """Collection-specific queries must parse without error."""
        from tests.search_helpers.query_generator import QueryGenerator

        for seed in seed_range:
            rng = random.Random(seed)
            gen = QueryGenerator(rng, supported_only=True, include_collection=True)
            query, _ = gen.generate()
            try:
                ast = parse_query(query)
                assert ast is not None
            except SearchError as e:
                pytest.fail(f"Seed {seed} generated unparseable query: {query!r}\n  Error: {e}")

    def test_collection_compile(self, seed_range):
        """Collection-specific queries must compile (no unsupported fallback)."""
        from tests.search_helpers.query_generator import QueryGenerator

        for seed in seed_range:
            rng = random.Random(seed)
            gen = QueryGenerator(rng, supported_only=True, include_collection=True)
            query, _ = gen.generate()
            ast = parse_query(query)
            compiled = compile_query(ast)
            assert "1=0" not in compiled.where_sql, (
                f"Seed {seed}: unsupported keyword in {query!r}"
            )

    def test_collection_execute(self, search_db, seed_range):
        """Collection-specific queries must execute in collection mode."""
        from tests.search_helpers.query_generator import QueryGenerator

        for seed in seed_range:
            rng = random.Random(seed)
            gen = QueryGenerator(rng, supported_only=True, include_collection=True)
            query, needs_collection = gen.generate()
            ast = parse_query(query)
            compiled = compile_query(ast)
            mode = "collection" if needs_collection else "all"
            try:
                rows, _ = execute_search(search_db, compiled, mode=mode)
                assert isinstance(rows, list)
            except Exception as e:
                pytest.fail(f"Seed {seed}: SQL error for {query!r} (mode={mode})\n  Error: {e}")


@pytest.mark.generative
@pytest.mark.scryfall
class TestGenerativeScryfall:
    """Compare generated query results with Scryfall API (report mode).

    Only generates standard (non-collection) keywords since Scryfall
    doesn't understand our collection extensions.
    """

    def test_results_report(self, search_db, known_oracle_ids,
                            scryfall_cache, seed_range):
        """Run generated queries against both local and Scryfall, write disagreement report."""
        from tests.search_helpers.query_generator import QueryGenerator
        from tests.search_helpers.result_comparator import compare_results
        from tests.search_helpers.scryfall_client import scryfall_search

        disagreements = []
        skipped = 0
        total = 0

        for seed in seed_range:
            total += 1
            rng = random.Random(seed)
            gen = QueryGenerator(rng, supported_only=True)
            query, _ = gen.generate()

            # Local execution
            ast = parse_query(query)
            compiled = compile_query(ast)
            try:
                rows, _ = execute_search(search_db, compiled, mode="all")
            except Exception:
                skipped += 1
                continue

            # Scryfall execution
            result = scryfall_search(scryfall_cache, query)
            if result["status_code"] != 200:
                skipped += 1
                continue

            # Compare
            comparison = compare_results(
                query, seed, rows, result["cards"], known_oracle_ids,
                scryfall_total=result["total_cards"],
            )
            if not comparison.passed:
                disagreements.append({
                    "seed": seed,
                    "query": query,
                    "local_count": len(comparison.local_ids),
                    "scryfall_count": len(comparison.scryfall_ids),
                    "scryfall_total": result["total_cards"],
                    "truncated": comparison.truncated,
                    "local_only_count": len(comparison.local_only),
                    "scryfall_only_count": len(comparison.scryfall_only),
                    "local_only_sample": list(comparison.local_only)[:5],
                    "scryfall_only_sample": list(comparison.scryfall_only)[:5],
                })

        # Classify disagreements
        # "real" = local_only > 0 AND not truncated (we returned cards Scryfall didn't)
        # "truncated" = Scryfall paginated, local_only not meaningful
        # "coverage" = only scryfall_only > 0 (Scryfall matched printings not in our fixture)
        real_bugs = [d for d in disagreements
                     if d["local_only_count"] > 0 and not d.get("truncated")]
        coverage_gaps = [d for d in disagreements
                         if d["local_only_count"] == 0 and not d.get("truncated")]

        # Write report (overwrite each run)
        report_path = pathlib.Path(__file__).parent / ".scryfall_disagreements.json"
        compared = total - skipped
        report = {
            "total_seeds": total,
            "skipped": skipped,
            "compared": compared,
            "disagreements": len(disagreements),
            "real_bugs": len(real_bugs),
            "coverage_gaps": len(coverage_gaps),
            "agreement_rate": (
                f"{(compared - len(real_bugs)) / max(compared, 1) * 100:.1f}%"
            ),
            "details": disagreements[:50],
        }
        report_path.write_text(json.dumps(report, indent=2))

        # Report mode: always pass, just log
        print(f"\n  Scryfall comparison: {compared} compared, {skipped} skipped")
        print(f"  Real bugs (local_only > 0): {len(real_bugs)}")
        print(f"  Coverage gaps (scryfall-only, fixture missing printings): {len(coverage_gaps)}")
        print(f"  Agreement rate (excluding coverage gaps): {report['agreement_rate']}")
        print(f"  Report: {report_path}")
        if real_bugs:
            print(f"  First real bug: seed={real_bugs[0]['seed']}, "
                  f"query={real_bugs[0]['query']!r}")
