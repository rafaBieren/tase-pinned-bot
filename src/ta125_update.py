import os
import asyncio
from datetime import datetime, date
from zoneinfo import ZoneInfo
from typing import Optional, Tuple

import pandas as pd
import yfinance as yf
from telegram import Bot


def _to_local_index(idx: pd.DatetimeIndex, tz_name: str) -> pd.DatetimeIndex:
    tz = ZoneInfo(tz_name)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    return idx.tz_convert(tz)


async def fetch_prev_close_daily(symbols: list[str], tz_name: str = "Asia/Jerusalem") -> Tuple[float, date]:
    """Return previous trading day's close and its local date.

    Tries each symbol up to 3 attempts with backoff between attempts.
    Uses history(period="5d", interval="1d"). Ensures date comparison in tz.
    """
    delays = [1, 2]
    last_error: Optional[BaseException] = None
    for attempt in range(3):
        for symbol in symbols:
            try:
                hist = yf.Ticker(symbol).history(period="5d", interval="1d", auto_adjust=False)
                if hist is None or hist.empty or "Close" not in hist.columns:
                    continue
                closes = hist[["Close"]].dropna()
                if closes.empty:
                    continue
                local_idx = _to_local_index(closes.index, tz_name)
                closes = closes.copy()
                closes.index = local_idx
                today_local = datetime.now(ZoneInfo(tz_name)).date()
                before_today = closes[closes.index.date < today_local]
                if before_today.empty:
                    # Not enough data before today
                    continue
                prev_close = float(before_today["Close"].iloc[-1])
                prev_date = before_today.index[-1].date()
                return prev_close, prev_date
            except Exception as exc:
                last_error = exc
                continue
        if attempt < len(delays):
            await asyncio.sleep(delays[attempt])
    raise RuntimeError("Failed to fetch previous close (daily)") from last_error


async def fetch_last_two_daily(symbols: list[str], tz_name: str = "Asia/Jerusalem") -> Tuple[float, date, float]:
    """Return (last_close, last_close_local_date, prev_close) from daily 1d series.

    Tries each symbol up to 3 attempts with backoff between attempts.
    """
    delays = [1, 2]
    last_error: Optional[BaseException] = None
    for attempt in range(3):
        for symbol in symbols:
            try:
                hist = yf.Ticker(symbol).history(period="7d", interval="1d", auto_adjust=False)
                if hist is None or hist.empty or "Close" not in hist.columns:
                    continue
                closes = hist[["Close"]].dropna()
                if len(closes) < 2:
                    continue
                local_idx = _to_local_index(closes.index, tz_name)
                closes = closes.copy()
                closes.index = local_idx
                last_close = float(closes["Close"].iloc[-1])
                prev_close = float(closes["Close"].iloc[-2])
                last_date = closes.index[-1].date()
                return last_close, last_date, prev_close
            except Exception as exc:
                last_error = exc
                continue
        if attempt < len(delays):
            await asyncio.sleep(delays[attempt])
    raise RuntimeError("Failed to fetch last two closes (daily)") from last_error


async def fetch_intraday_last_today(symbols: list[str], tz_name: str = "Asia/Jerusalem") -> Optional[float]:
    """Return latest minute-close from today's intraday, or None if no data today.

    Uses history(period="2d", interval="1m"). Ensures local date filtering.
    Tries each symbol up to 3 attempts with backoff between attempts.
    """
    delays = [1, 2]
    last_error: Optional[BaseException] = None
    for attempt in range(3):
        for symbol in symbols:
            try:
                hist = yf.Ticker(symbol).history(period="2d", interval="1m", auto_adjust=False)
                if hist is None or hist.empty or "Close" not in hist.columns:
                    continue
                intraday = hist[["Close"]].dropna()
                if intraday.empty:
                    continue
                local_idx = _to_local_index(intraday.index, tz_name)
                intraday = intraday.copy()
                intraday.index = local_idx
                today_local = datetime.now(ZoneInfo(tz_name)).date()
                today_rows = intraday[intraday.index.date == today_local]
                if today_rows.empty:
                    # No ticks today (e.g., weekend/holiday/after-hours)
                    continue
                last_today = float(today_rows["Close"].iloc[-1])
                return last_today
            except Exception as exc:
                last_error = exc
                continue
        if attempt < len(delays):
            await asyncio.sleep(delays[attempt])
    # If no data for today across attempts/symbols, return None (not an error)
    return None


def compute_change(prev: float, last: float) -> Tuple[float, float]:
    abs_change = last - prev
    pct_change = (abs_change / prev * 100.0) if prev else 0.0
    return abs_change, pct_change


def _arrow_for(pct_change: float) -> str:
    if abs(pct_change) < 0.005:
        return "■"
    return "▲" if pct_change > 0 else "▼"


def format_message_today(last_price: float, abs_change: float, pct_change: float, now_local_dt: datetime) -> str:
    arrow = _arrow_for(pct_change)
    return (
        "מדד ת״א-125 היום: {arrow} {pct:+.2f}% ({abs:+.1f} נק׳) ל-{last:,.1f} נק׳. נכון ל-{stamp}."
    ).format(
        arrow=arrow,
        pct=pct_change,
        abs=abs_change,
        last=last_price,
        stamp=now_local_dt.strftime("%d/%m/%Y %H:%M"),
    )


def format_message_last_trading_day(last_close: float, abs_change: float, pct_change: float, last_close_date: date) -> str:
    arrow = _arrow_for(pct_change)
    return (
        "מדד ת״א-125 ביום המסחר האחרון ({d}): {arrow} {pct:+.2f}% ({abs:+.1f} נק׳) ל-{last:,.1f} נק׳."
    ).format(
        d=last_close_date.strftime("%d/%m/%Y"),
        arrow=arrow,
        pct=pct_change,
        abs=abs_change,
        last=last_close,
    )


async def send_ta125_update(chat_id: str, bot: Optional[Bot] = None) -> None:
    """Build and send TA‑125 change message, preferring today's intraday if available."""
    close_bot = False
    if bot is None:
        token_env = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
        if not token_env:
            raise SystemExit("Missing TELEGRAM_BOT_TOKEN in environment or .env")
        bot = Bot(token=token_env)
        close_bot = True

    symbols = ["^TA125.TA", "TA125.TA", "^TA125", "^TA-125.TA"]
    tz_name = "Asia/Jerusalem"

    try:
        prev_close, _ = await fetch_prev_close_daily(symbols, tz_name)
        last_today = await fetch_intraday_last_today(symbols, tz_name)
        if last_today is not None:
            abs_change, pct_change = compute_change(prev_close, last_today)
            text = format_message_today(
                last_price=last_today,
                abs_change=abs_change,
                pct_change=pct_change,
                now_local_dt=datetime.now(ZoneInfo(tz_name)),
            )
        else:
            last_close, last_date, prev_close2 = await fetch_last_two_daily(symbols, tz_name)
            abs_change, pct_change = compute_change(prev_close2, last_close)
            text = format_message_last_trading_day(
                last_close=last_close,
                abs_change=abs_change,
                pct_change=pct_change,
                last_close_date=last_date,
            )
    except Exception:
        text = "לא הצלחתי להביא כרגע את שינוי מדד ת״א-125. נסו שוב מאוחר יותר."

    await bot.send_message(chat_id=chat_id, text=text)

    if close_bot:
        await bot.close()
