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
    """Assemble the full HTML message body."""
    now = pendulum.now(tz).format("HH:mm")
    lines = [f"<b>מדדי ת״א – שינוי יומי</b> <i>(עודכן: {now})</i>"]
    for q in quotes:
        lines.append(f"• {q.name}: {_fmt_pct(q.change_pct)} ({_fmt_num(q.price, 2)})")
    lines.append("<i>הערה: ייתכן עיכוב קטן בעדכון הנתונים.</i>")
    return "\n".join(lines)
