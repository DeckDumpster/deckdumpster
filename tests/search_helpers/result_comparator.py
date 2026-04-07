"""Printing ID set comparison between local search and Scryfall results."""

from dataclasses import dataclass, field


@dataclass
class ComparisonResult:
    """Result of comparing local vs Scryfall search results."""

    query: str
    seed: int
    local_ids: frozenset = field(default_factory=frozenset)
    scryfall_ids: frozenset = field(default_factory=frozenset)
    local_only: frozenset = field(default_factory=frozenset)
    scryfall_only: frozenset = field(default_factory=frozenset)
    passed: bool = True
    truncated: bool = False  # Scryfall returned fewer cards than total_cards

    def summary(self) -> str:
        parts = [f"seed={self.seed}, query={self.query!r}"]
        if self.truncated:
            parts.append("  (Scryfall results truncated — local_only not meaningful)")
        if self.local_only and not self.truncated:
            parts.append(f"  local_only ({len(self.local_only)}): too loose")
        if self.scryfall_only:
            parts.append(f"  scryfall_only ({len(self.scryfall_only)}): too strict")
        return "\n".join(parts)


def compare_results(
    query: str,
    seed: int,
    local_rows: list,
    scryfall_cards: list,
    known_oracle_ids: frozenset,
    scryfall_total: int = 0,
) -> ComparisonResult:
    """Compare local search results with Scryfall results.

    Scryfall defaults to unique:cards (one result per oracle identity).
    We return unique:prints (all printings). To compare fairly, we
    deduplicate both sides by oracle_id and only compare cards that
    exist in our local DB.
    """
    # Deduplicate to oracle_id (Scryfall's unique:cards default)
    local_ids = frozenset(
        row["oracle_id"] for row in local_rows if row["oracle_id"]
    )
    scryfall_ids = frozenset(
        card["oracle_id"] for card in scryfall_cards
        if "oracle_id" in card
    )

    # Intersect with known universe
    local_in_known = local_ids & known_oracle_ids
    scryfall_in_known = scryfall_ids & known_oracle_ids

    local_only = local_in_known - scryfall_in_known
    scryfall_only = scryfall_in_known - local_in_known

    # If Scryfall truncated results, local_only is not meaningful
    truncated = scryfall_total > len(scryfall_cards)
    if truncated:
        passed = len(scryfall_only) == 0
    else:
        passed = len(local_only) == 0 and len(scryfall_only) == 0

    return ComparisonResult(
        query=query,
        seed=seed,
        local_ids=local_in_known,
        scryfall_ids=scryfall_in_known,
        local_only=local_only,
        scryfall_only=scryfall_only,
        passed=passed,
        truncated=truncated,
    )
