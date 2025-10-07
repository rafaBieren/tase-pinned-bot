"""
tase_calendar.py
----------------
Provides tools to check TASE trading hours based on a hardcoded schedule for 2025-2026.
This module accounts for Israeli holidays, shortened trading days, and the planned
change in trading days from 2026.
"""

from __future__ import annotations
from datetime import date, datetime, time
from typing import Optional, Tuple

# TASE holidays for 2025 (no trading)
_HOLIDAYS_2025 = {
    date(2025, 4, 13),   # Passover I
    date(2025, 4, 30),   # Memorial Day
    date(2025, 5, 1),    # Independence Day
    date(2025, 6, 2),    # Shavuot
    date(2025, 8, 3),    # Tisha B'Av
    date(2025, 9, 22),   # Erev Rosh Hashanah
    date(2025, 9, 23),   # Rosh Hashanah I
    date(2025, 9, 24),   # Rosh Hashanah II
    date(2025, 10, 1),   # Erev Yom Kippur
    date(2025, 10, 2),   # Yom Kippur
    date(2025, 10, 6),   # Erev Sukkot
    date(2025, 10, 7),   # Sukkot I
    date(2025, 10, 13),  # Erev Simchat Torah
    date(2025, 10, 14),  # Simchat Torah
}

# Shortened trading days for 2025 (e.g., Chol HaMoed)
_SHORT_DAYS_2025 = {
    date(2025, 4, 14), date(2025, 4, 15), date(2025, 4, 16), date(2025, 4, 17),  # Chol HaMoed Pesach
    date(2025, 10, 8), date(2025, 10, 9), date(2025, 10, 12),                    # Chol HaMoed Sukkot
}

# TASE holidays for 2026 (no trading)
_HOLIDAYS_2026 = {
    date(2026, 4, 2),    # Passover I
    date(2026, 4, 8),    # Passover VII
    date(2026, 4, 21),   # Memorial Day
    date(2026, 4, 22),   # Independence Day
    date(2026, 5, 22),   # Shavuot
    date(2026, 7, 23),   # Tisha B'Av
    date(2026, 9, 11),   # Erev Rosh Hashanah
    date(2026, 9, 21),   # Yom Kippur
    date(2026, 9, 25),   # Erev Sukkot
    date(2026, 10, 1),   # Erev Simchat Torah
    date(2026, 10, 2),   # Simchat Torah
}

# Shortened trading days for 2026 (e.g., Chol HaMoed)
_SHORT_DAYS_2026 = {
    date(2026, 4, 6), date(2026, 4, 7),                                      # Chol HaMoed Pesach
    date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30),                 # Chol HaMoed Sukkot
}

def is_trading_day(moment: datetime) -> bool:
    """Check if a given datetime is a trading day, considering weekends and holidays."""
    d = moment.date()
    year = d.year
    weekday = d.weekday()

    holidays = set()
    if year == 2025:
        holidays = _HOLIDAYS_2025
    elif year == 2026:
        holidays = _HOLIDAYS_2026
    
    if d in holidays:
        return False

    # Note: the check for the first trading day of 2026 (Jan 5) is implicitly handled
    # by the weekday check below.
    if year < 2026 or (year == 2026 and d.month == 1 and d.day < 5):
        # Before Jan 5, 2026, trading is Sunday (6) to Thursday (3)
        return weekday in {6, 0, 1, 2, 3}
    else:
        # From Jan 5, 2026, trading is Monday (0) to Friday (4)
        return weekday in {0, 1, 2, 3, 4}

def get_trading_hours(moment: datetime) -> Optional[Tuple[time, time]]:
    """Get the start and stop trading times for a given datetime."""
    if not is_trading_day(moment):
        return None

    d = moment.date()
    year = d.year
    weekday = d.weekday()
    start_time = time(9, 25)

    # Check for shortened trading days (Chol HaMoed)
    if (year == 2025 and d in _SHORT_DAYS_2025) or \
       (year == 2026 and d in _SHORT_DAYS_2026):
        return start_time, time(14, 25)

    # Regular trading hours
    if year < 2026 or (year == 2026 and d.month == 1 and d.day < 5):
        # Schedule until Jan 5, 2026 (Sun-Thu)
        if weekday == 6:  # Sunday
            stop_time = time(15, 50)
        else:  # Monday to Thursday
            stop_time = time(17, 25)
    else:
        # Schedule from Jan 5, 2026 onwards (Mon-Fri)
        if weekday == 4:  # Friday
            stop_time = time(13, 50)
        else:  # Monday to Thursday
            stop_time = time(17, 25)

    return start_time, stop_time
