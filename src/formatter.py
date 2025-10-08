"""
formatter.py
------------
Builds the HTML-formatted message text for Telegram.

Responsibilities:
- Formatting numbers and percentages consistently
- Injecting an "Updated at HH:MM" line with the configured timezone
"""

from __future__ import annotations
from typing import Iterable, Optional
import pendulum
from tase_calendar import TradingDayInfo


def _fmt_num(x: float, digits: int = 2) -> str:
    """Format a number with thousands separators and fixed decimals."""
    return f"{x:,.{digits}f}"


def _fmt_pct(x: float, digits: int = 2) -> str:
    """Format a percentage with an explicit sign."""
    sign = "+" if x >= 0 else ""
    return f"{sign}{x:.{digits}f}%"


def build_message(
    quotes: Iterable,
    tz: str,
    market_closed: bool = False,
    day_info: Optional[TradingDayInfo] = None,
) -> str:
    """Assemble the full MarkdownV2 message body."""
    header = []
    day_info = day_info or TradingDayInfo(is_trading=not market_closed)

    # Add a note for shortened trading days
    if day_info.is_trading and day_info.is_short:
        stop_time_str = day_info.stop_time.strftime("%H:%M")
        reason_str = f" \\({day_info.reason}\\)" if day_info.reason else ""
        # Calculate the time 20 minutes before stop_time
        stop_hour, stop_minute = map(int, stop_time_str.split(':'))
        total_minutes = stop_hour * 60 + stop_minute - 20
        adjusted_hour, adjusted_minute = divmod(total_minutes, 60)
        adjusted_stop_time = f"{adjusted_hour:02d}:{adjusted_minute:02d}"
        header.append(f"_יום מסחר מקוצר עד {adjusted_stop_time}{reason_str}_")

    # Special message for non-trading days
    if not day_info.is_trading and day_info.reason:
        header.append(f"*{day_info.reason}*")
        header.append(f"_אין מסחר היום_")
        lines = header
    # Regular trading day, but market is currently closed
    elif market_closed:
        first_quote = next(iter(quotes), None)
        if first_quote and first_quote.price_date:
            date_str = pendulum.instance(first_quote.price_date).in_timezone(tz).format("DD/MM/YYYY")
            header.append("*המסחר בבורסה סגור כעת\\.*")
            header.append(f"*הנתונים מעודכנים ליום המסחר האחרון \\({date_str}\\)*")
        else:
            header.append("*המסחר בבורסה סגור כעת\\.*")
            header.append("*הנתונים מעודכנים ליום המסחר האחרון\\.*")
        
        header.append("")
        header.append("*מדדי ת״א – סגירה* 📊📉📈")
        lines = header
    # Regular, open trading day
    else:
        now = pendulum.now(tz).format("HH:mm")
        title = f"*מדדי ת״א – שינוי יומי* _\\(עודכן: {now}\\)_ 📊📉📈"
        
        header.append(title)
        lines = header

    # Don't add index data if it's a non-trading day
    if day_info.is_trading:
        for q in quotes:
            # Choose emoji based on change percentage
            if q.change_pct > 0:
                emoji = "🟢"
            elif q.change_pct < 0:
                emoji = "🔴"
            else:
                emoji = "⚪"
            # Escape special characters for MarkdownV2
            name_escaped = q.name.replace("-", "\\-")
            price_formatted = _fmt_num(q.price, 2).replace(",", "\\,").replace(".", "\\.")
            pct_formatted = _fmt_pct(q.change_pct).replace(".", "\\.").replace("+", "\\+").replace("-", "\\-")
            lines.append(f"{emoji} {name_escaped}: {pct_formatted} \\({price_formatted}\\)")
        lines.append("_הערה: ייתכן עיכוב של עד 15 דקות בעדכון הנתונים\\._")
    
    # Add separator and promotional content
    lines.append("")

    lines.append("*הטבה לפתיחת חשבון מסחר במיטב טרייד* 📈: https://bit\\.ly/ValueInvestingInIsrael")
    lines.append("*הטבה לחברי הקהילה עם סוכן פיננסי \\+ החזר מס בתנאים מעולים* 💰: https://surense\\.com/app/p/BcR6zrV")
    lines.append("")
    lines.append("*השקעות ערך בישראל* 🇮🇱: https://t\\.me/israelValueInvestments")
    lines.append("*קבוצת הדיונים*: https://t\\.me/ValueInvestingIsrael")
    
    return "\n".join(lines)
