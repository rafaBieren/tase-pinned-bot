"""
tase_calendar.py
----------------
Provides tools to check TASE trading hours based on a hardcoded schedule for 2025-2026.
This module accounts for Israeli holidays, shortened trading days, and the planned
change in trading days from 2026.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Optional, Tuple

@dataclass
class TradingDayInfo:
    """Holds all relevant information about a trading day's schedule."""
    is_trading: bool
    is_short: bool = False
    reason: Optional[str] = None
    start_time: Optional[time] = None
    stop_time: Optional[time] = None

# TASE holidays for 2025 (no trading)
_HOLIDAYS_2025 = {
    date(2025, 4, 13): "פסח",
    date(2025, 4, 30): "יום הזיכרון",
    date(2025, 5, 1): "יום העצמאות",
    date(2025, 6, 2): "שבועות",
    date(2025, 8, 3): "תשעה באב",
    date(2025, 9, 22): "ערב ראש השנה",
    date(2025, 9, 23): "ראש השנה",
    date(2025, 9, 24): "ראש השנה",
    date(2025, 10, 1): "ערב יום כיפור",
    date(2025, 10, 2): "יום כיפור",
    date(2025, 10, 6): "ערב סוכות",
    date(2025, 10, 7): "סוכות",
    date(2025, 10, 13): "ערב שמחת תורה",
    date(2025, 10, 14): "שמחת תורה",
}

# Shortened trading days for 2025
_SHORT_DAYS_2025 = {
    date(2025, 4, 14): "חול המועד פסח",
    date(2025, 4, 15): "חול המועד פסח",
    date(2025, 4, 16): "חול המועד פסח",
    date(2025, 4, 17): "חול המועד פסח",
    date(2025, 10, 8): "חול המועד סוכות",
    date(2025, 10, 9): "חול המועד סוכות",
    date(2025, 10, 12): "חול המועד סוכות",
}

# TASE holidays for 2026 (no trading)
_HOLIDAYS_2026 = {
    date(2026, 4, 2): "פסח",
    date(2026, 4, 8): "שביעי של פסח",
    date(2026, 4, 21): "יום הזיכרון",
    date(2026, 4, 22): "יום העצמאות",
    date(2026, 5, 22): "שבועות",
    date(2026, 7, 23): "תשעה באב",
    date(2026, 9, 11): "ערב ראש השנה",
    date(2026, 9, 21): "יום כיפור",
    date(2026, 9, 25): "ערב סוכות",
    date(2026, 10, 1): "ערב שמחת תורה",
    date(2026, 10, 2): "שמחת תורה",
}

# Shortened trading days for 2026
_SHORT_DAYS_2026 = {
    date(2026, 4, 6): "חול המועד פסח",
    date(2026, 4, 7): "חול המועד פסח",
    date(2026, 9, 28): "חול המועד סוכות",
    date(2026, 9, 29): "חול המועד סוכות",
    date(2026, 9, 30): "חול המועד סוכות",
}


def get_trading_day_info(moment: datetime) -> TradingDayInfo:
    """
    Get all schedule-related information for a given datetime.
    This is the main entry point for the calendar module.
    """
    d = moment.date()
    year = d.year
    weekday = d.weekday()

    # Check for holidays
    holidays = _HOLIDAYS_2025 if year == 2025 else _HOLIDAYS_2026
    if d in holidays:
        return TradingDayInfo(is_trading=False, reason=holidays[d])

    # Determine trading day based on week structure
    is_trading_weekday = False
    if year < 2026 or (year == 2026 and d.month == 1 and d.day < 5):
        # Before Jan 5, 2026, trading is Sunday (6) to Thursday (3)
        if weekday in {6, 0, 1, 2, 3}:
            is_trading_weekday = True
    else:
        # From Jan 5, 2026, trading is Monday (0) to Friday (4)
        if weekday in {0, 1, 2, 3, 4}:
            is_trading_weekday = True
            
    if not is_trading_weekday:
        return TradingDayInfo(is_trading=False, reason="סוף שבוע")

    # If we are here, it's a trading day. Now let's get the hours.
    start_time = time(9, 25)

    # Check for shortened trading days (Chol HaMoed)
    short_days = _SHORT_DAYS_2025 if year == 2025 else _SHORT_DAYS_2026
    if d in short_days:
        return TradingDayInfo(
            is_trading=True,
            is_short=True,
            reason=short_days[d],
            start_time=start_time,
            stop_time=time(14, 45) # stop the bot 20 minutes after the end of the trading day because of the delay in the data
        )

    # Regular trading hours
    stop_time = None
    if year < 2026 or (year == 2026 and d.month == 1 and d.day < 5):
        # Schedule until Jan 5, 2026 (Sun-Thu)
        if weekday == 6:  # Sunday
            stop_time = time(15, 50)
        else:  # Monday to Thursday
            stop_time = time(17, 45) # stop the bot 20 minutes after the end of the trading day because of the delay in the data
    else:
        # Schedule from Jan 5, 2026 onwards (Mon-Fri)
        if weekday == 4:  # Friday
            stop_time = time(13, 50)
        else:  # Monday to Thursday
            stop_time = time(17, 45) # stop the bot 20 minutes after the end of the trading day because of the delay in the data
            
    return TradingDayInfo(
        is_trading=True,
        start_time=start_time,
        stop_time=stop_time
    )
