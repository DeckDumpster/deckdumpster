"""Collector numbers as a single sortable integer.

`ORDER BY CAST(collector_number AS INTEGER), collector_number` — what
`/api/set-browse` does today — puts `A-248` *first* in every Alchemy-touched
set, because `CAST('A-248' AS INTEGER)` is 0.  A binder grid is a set laid out
in collector-number order, so getting that order wrong is the whole feature
going wrong.

The alternative is sorting in Python after fetching the set (what pokedumpster's
`binder.rs:375-392` does).  This encoding exists instead so the order can be
read off an index, because doing the work at ingest rather than at request time
is the governing rule of the design this belongs to.

The encoding is namespace, then numeric value, then suffix:

    123     -> n * 100                             123   -> 12300
    123a    -> n * 100 + ord(suffix) - ord('a') + 1  123a -> 12301, 123b -> 12302
    123*    -> n * 100 + 50                        123★ -> 12350
    A-123   -> 1_000_000 + n * 100                 A-248 -> 1_024_800
    S123    -> 2_000_000 + n * 100                 S123  -> 2_012_300
    other   -> 3_000_000 + leading digits * 100

`* 100` reserves suffix room without a second column, and puts the prerelease
stamp (+50) after every lettered variant (a..z is +1..+26) at the same number.

Two consequences worth stating, because both are load-bearing:

**The value is a pure function of the string.**  Not of a rowid — deployed
instances shadow `printings` with a temp view over an ATTACHed shared
catalogue, and views resolve `rowid` to NULL rather than erroring, so anything
keyed on it would silently sort into one heap.  It also means a rebuild is
idempotent, and that a shared catalogue and a local one agree.

**The namespace stride bounds the numeric part at 9,999.**  A five-digit
collector number would encode into the namespace above its own.  The largest
collector number in the 7,645-printing fixture is 780, and MTG's largest real
set is 779 printings, so the headroom is three orders of magnitude.

The order is not total on its own — `A-150e` matches no shape above and lands
in the `other` bucket alongside anything else exotic.  Every query that uses
this column closes its `ORDER BY` on `printing_id`, which is what makes the
order total; see `idx_printings_set_sortable`.
"""

import re

#: Distance between namespaces.  Also the ceiling on `n * 100`.
NAMESPACE_STRIDE = 1_000_000

#: Room reserved below the next collector number for suffixes.
SUFFIX_ROOM = 100

#: Where the prerelease/promo stamp sorts within a number: after every letter.
STAMP_OFFSET = 50

_PLAIN = re.compile(r"(\d+)\Z")
_LETTERED = re.compile(r"(\d+)([a-z])\Z")
_STAMPED = re.compile(r"(\d+)★\Z")
_ALCHEMY = re.compile(r"A-(\d+)\Z")
_STARTER = re.compile(r"S(\d+)\Z")
_LEADING_DIGITS = re.compile(r"(\d+)")


def number_sortable(collector_number: str) -> int:
    """Encode a collector number so SQL can sort a set into binder order.

    Pure function of the string; see the module docstring for the table.
    """
    cn = collector_number.strip()

    match = _PLAIN.fullmatch(cn)
    if match:
        return int(match.group(1)) * SUFFIX_ROOM

    match = _LETTERED.fullmatch(cn)
    if match:
        number, suffix = match.groups()
        return int(number) * SUFFIX_ROOM + ord(suffix) - ord("a") + 1

    match = _STAMPED.fullmatch(cn)
    if match:
        return int(match.group(1)) * SUFFIX_ROOM + STAMP_OFFSET

    match = _ALCHEMY.fullmatch(cn)
    if match:
        return NAMESPACE_STRIDE + int(match.group(1)) * SUFFIX_ROOM

    match = _STARTER.fullmatch(cn)
    if match:
        return 2 * NAMESPACE_STRIDE + int(match.group(1)) * SUFFIX_ROOM

    digits = _LEADING_DIGITS.search(cn)
    leading = int(digits.group(1)) if digits else 0
    return 3 * NAMESPACE_STRIDE + leading * SUFFIX_ROOM
