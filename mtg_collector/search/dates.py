"""Date-value parsing for the search compiler.

Translates user-facing date inputs into UTC datetime ranges suitable for
comparing against ``collection.acquired_at`` (which is stored as ISO 8601
UTC strings).

Accepted inputs (case-insensitive for aliases):
    Aliases:    ``today``, ``yesterday``
    Relative:   ``Nd``, ``Nw``, ``Nm``, ``Ny`` (N days/weeks/months/years ago)
    ISO date:   ``YYYY``, ``YYYY-MM``, ``YYYY-MM-DD``
    ISO datetime: ``YYYY-MM-DDTHH:MM[:SS[.f]][Z|+HH:MM]``

All resolution happens in the user's local timezone so that
``added:today`` matches cards added during the user's calendar day rather
than the UTC day.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_REL_RE = re.compile(r"^(\d+)([dwmy])$")
_YEAR_RE = re.compile(r"^\d{4}$")
_YEAR_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_YEAR_MONTH_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 19-char prefix of acquired_at (YYYY-MM-DDTHH:MM:SS) is what we compare
# against. Using a fixed-width prefix sidesteps lex ordering issues caused
# by the trailing ``Z`` vs ``+00:00`` vs fractional seconds.
ACQUIRED_AT_PREFIX_LEN = 19


def resolve_tz(tz: str | None) -> ZoneInfo:
    """Return a ZoneInfo for ``tz``. Falls back to UTC if unknown/missing.

    Why: clients send IANA names via Intl API; defensive callers may pass
    None or junk. UTC is the safe default.
    """
    if not tz:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def parse_date_value(val: str, tz: str | None = None) -> tuple[str, str] | None:
    """Parse a user date value into a UTC ``[start, end)`` prefix pair.

    Returns ``(start_prefix, end_prefix)`` where each is a 19-char string
    ``YYYY-MM-DDTHH:MM:SS`` suitable for direct comparison against
    ``SUBSTR(c.acquired_at, 1, 19)``. ``end`` is exclusive.

    Returns ``None`` when the input cannot be parsed.
    """
    if not val:
        return None
    lz = resolve_tz(tz)
    lower = val.strip().lower()

    today_local = datetime.now(lz).date()

    if lower == "today":
        return _day_range(today_local, lz)
    if lower == "yesterday":
        return _day_range(today_local - timedelta(days=1), lz)

    m = _REL_RE.match(lower)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if unit == "d":
            return _day_range(today_local - timedelta(days=n), lz)
        if unit == "w":
            return _day_range(today_local - timedelta(weeks=n), lz)
        if unit == "m":
            return _day_range(_subtract_months(today_local, n), lz)
        if unit == "y":
            return _day_range(_subtract_years(today_local, n), lz)

    if _YEAR_RE.match(val):
        y = int(val)
        if not (1 <= y <= 9999):
            return None
        start = datetime(y, 1, 1, tzinfo=lz)
        end = datetime(y + 1, 1, 1, tzinfo=lz) if y < 9999 else datetime(9999, 12, 31, 23, 59, 59, tzinfo=lz)
        return _utc_prefix_pair(start, end)

    if _YEAR_MONTH_RE.match(val):
        y, mo = (int(x) for x in val.split("-"))
        if not (1 <= mo <= 12):
            return None
        start = datetime(y, mo, 1, tzinfo=lz)
        if mo == 12:
            end = datetime(y + 1, 1, 1, tzinfo=lz)
        else:
            end = datetime(y, mo + 1, 1, tzinfo=lz)
        return _utc_prefix_pair(start, end)

    if _YEAR_MONTH_DAY_RE.match(val):
        try:
            d = date.fromisoformat(val)
        except ValueError:
            return None
        return _day_range(d, lz)

    # Full ISO datetime (treat naive as local-tz).
    try:
        # fromisoformat in 3.10 does not accept trailing Z; normalize.
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=lz)
    # A precise datetime is treated as a point match at second precision.
    start_utc = dt.astimezone(timezone.utc)
    end_utc = start_utc + timedelta(seconds=1)
    return (_fmt_prefix(start_utc), _fmt_prefix(end_utc))


def _day_range(d: date, lz: ZoneInfo) -> tuple[str, str]:
    """[start, end) covering the full local day, expressed as UTC prefixes."""
    start = datetime.combine(d, time.min).replace(tzinfo=lz)
    end = start + timedelta(days=1)
    return _utc_prefix_pair(start, end)


def _utc_prefix_pair(start: datetime, end: datetime) -> tuple[str, str]:
    return (_fmt_prefix(start.astimezone(timezone.utc)),
            _fmt_prefix(end.astimezone(timezone.utc)))


def _fmt_prefix(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _subtract_months(d: date, n: int) -> date:
    y = d.year
    m = d.month - n
    while m <= 0:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    last_day = calendar.monthrange(y, m)[1]
    return date(y, m, min(d.day, last_day))


def _subtract_years(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year - n)
    except ValueError:
        # Feb 29 in a non-leap year — clamp to Feb 28.
        return d.replace(year=d.year - n, day=28)
