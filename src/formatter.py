"""
formatter.py
------------
Builds the HTML-formatted message text for Telegram.

Responsibilities:
- Formatting numbers and percentages consistently
- Injecting an "Updated at HH:MM" line with the configured timezone
"""

from __future__ import annotations
from typing import Iterable
import pendulum


def _fmt_num(x: float, digits: int = 2) -> str:
    """Format a number with thousands separators and fixed decimals."""
    return f"{x:,.{digits}f}"


def _fmt_pct(x: float, digits: int = 2) -> str:
    """Format a percentage with an explicit sign."""
    sign = "+" if x >= 0 else ""
    return f"{sign}{x:.{digits}f}%"


def build_message(quotes: Iterable, tz: str) -> str:
    """Assemble the full MarkdownV2 message body."""
    now = pendulum.now(tz).format("HH:mm")
    lines = [f"*מדדי ת״א – שינוי יומי* _\\(עודכן: {now}\\)_"]
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
        pct_formatted = _fmt_pct(q.change_pct).replace(".", "\\.").replace("+", "\\+")
        lines.append(f"{emoji} {name_escaped}: {pct_formatted} \\({price_formatted}\\)")
    lines.append("_הערה: ייתכן עיכוב קטן בעדכון הנתונים\\._")
    return "\n".join(lines)
