"""Deterministic move-in date resolution: ISO dates and common relative phrases (English + Hinglish).

The model passes the renter's phrase ("within a week", "agle mahine") and this code turns it into a date
relative to `today`, so the same words always give the same date (evals pin today via TODAY_OVERRIDE).
"""
from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import Optional

_NUM = {"a": 1, "an": 1, "one": 1, "ek": 1, "two": 2, "do": 2, "three": 3, "teen": 3, "four": 4, "char": 4,
        "five": 5, "paanch": 5, "six": 6, "ten": 10, "fifteen": 15}
_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m} | \
          {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m} | {"sept": 9}

_NOW = ("today", "immediately", "asap", "right away", "right now", "turant", "abhi", "aaj")
_WEEK = ("within a week", "in a week", "this week", "within the week", "next 7 days", "ek hafte", "is hafte", "hafte bhar")
_NEXT_WEEK = ("next week", "agle hafte", "agla hafta")
_NEXT_MONTH = ("next month", "agle mahine", "agla mahina")
_MONTH_END = ("end of this month", "end of the month", "month end", "is mahine ke end")


def _add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def resolve_date(text: str, today: date) -> Optional[date]:
    """Return the date the phrase means, or None if it isn't understood (the agent then asks)."""
    s = " ".join(text.lower().replace(",", " ").split())
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass
    if any(p in s for p in _MONTH_END):
        return date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    if any(p in s for p in _NEXT_MONTH):
        return _add_months(today, 1).replace(day=1)
    if any(p in s for p in _NEXT_WEEK) or any(p in s for p in _WEEK):
        return today + timedelta(days=7)
    if s in ("tomorrow", "kal") or "tomorrow" in s:
        return today + timedelta(days=1)
    if any(p == s or p in s.split() for p in _NOW) or any(p in s for p in ("right away", "right now")):
        return today

    # "in 10 days", "within two weeks", "3 mahine mein"
    m = re.search(r"(\d+|" + "|".join(_NUM) + r")\s*(day|days|din|week|weeks|hafte|hafton|month|months|mahine|mahina)\b", s)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else _NUM[m.group(1)]
        unit = m.group(2)
        if unit.startswith(("day", "din")):
            return today + timedelta(days=n)
        if unit.startswith(("week", "haft")):
            return today + timedelta(weeks=n)
        return _add_months(today, n)

    # "1st December", "December 1", "1 dec", "15 jan 2027"
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-z]+)(?:\s+(\d{4}))?", s) or \
        re.search(r"([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+(\d{4}))?", s)
    if m:
        a, b, year = m.groups()
        day_s, month_s = (a, b) if a.isdigit() else (b, a)
        month = _MONTHS.get(month_s)
        if month:
            y = int(year) if year else today.year
            try:
                d = date(y, month, int(day_s))
            except ValueError:
                return None
            if not year and d < today:
                d = d.replace(year=y + 1)  # "1st March" said in November means next March
            return d
    return None
