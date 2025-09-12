"""
indices.py
----------
Data fetching and basic transformation for index quotes.

For MVP we use `yfinance`:
- Fetch a recent intraday last price (1m/5m fallback).
- Fetch a previous close (from daily history) to compute daily % change.

If data is missing (common with certain symbols), we attempt a simple fallback
for TA-125 variants. You can extend `ALT_SYMBOLS` for other indices if needed.
"""

from __future__ import annotations
from typing import Optional, Iterable, List
import math
from loguru import logger
import os

# Work around yfinance's optional curl_cffi transport causing attribute errors in some environments
os.environ.setdefault("YF_USE_CURL_CFFI", "false")

import yfinance as yf


ALT_SYMBOLS = {
    # If the primary symbol fails, try alternatives in order
    "^TA125.TA": ["TA125.TA", "^TA100"],
    "TA125.TA": ["^TA125.TA", "^TA100"],
}


class IndexQuote:
    """In-memory representation of a single index quote and its derived fields."""

    def __init__(self, name: str, symbol: str, price: float, prev_close: float):
        self.name = name
        self.symbol = symbol
        self.price = float(price)
        self.prev_close = float(prev_close)

    @property
    def change_pct(self) -> float:
        """Daily percentage change vs previous close."""
        if self.prev_close and not math.isclose(self.prev_close, 0.0):
            return (self.price / self.prev_close - 1.0) * 100.0
        return 0.0


def _try_get_prev_close(symbol: str) -> Optional[float]:
    """Fetch previous close from recent daily candles."""
    hist = yf.download(symbol, period="7d", interval="1d", progress=False)
    if hist is None or hist.empty:
        return None
    # Ideally take the penultimate close (yesterday); otherwise the last available
    if len(hist["Close"]) >= 2:
        return float(hist["Close"].iloc[-2])
    return float(hist["Close"].iloc[-1])


def _try_get_last_price(symbol: str) -> Optional[float]:
    """Fetch the latest intraday close price with a simple fallback chain."""
    for period, interval in [("1d", "1m"), ("5d", "5m")]:
        hist = yf.download(symbol, period=period, interval=interval, progress=False)
        if hist is not None and not hist.empty:
            return float(hist["Close"].iloc[-1])

    # Fallback to fast_info if available
    try:
        t = yf.Ticker(symbol)
        fi = t.fast_info
        last = getattr(fi, "last_price", None) or getattr(fi, "lastPrice", None) or fi.get("last_price", None)
        if last is not None:
            return float(last)
    except Exception:
        pass

    return None


def fetch_index(name: str, symbol: str) -> Optional[IndexQuote]:
    """
    Fetch last price and previous close for one index.
    If primary symbol fails, try alternative symbols if configured.
    """
    try:
        last = _try_get_last_price(symbol)
        prev = _try_get_prev_close(symbol)

        # Try alternatives if needed
        if (last is None or prev is None) and symbol in ALT_SYMBOLS:
            for alt in ALT_SYMBOLS[symbol]:
                logger.warning(f"No data for {symbol}, trying alternative {alt}")
                last = last or _try_get_last_price(alt)
                prev = prev or _try_get_prev_close(alt)
                if last is not None and prev is not None:
                    symbol = alt
                    break

        if last is None or prev is None:
            logger.error(f"Failed fetching {name} ({symbol})")
            return None

        return IndexQuote(name=name, symbol=symbol, price=last, prev_close=prev)

    except Exception as e:
        logger.exception(f"Error fetching {name} ({symbol}): {e}")
        return None


def fetch_all(indices_map: dict[str, str]) -> List[IndexQuote]:
    """Fetch all indices defined in the configuration."""
    out: List[IndexQuote] = []
    for name, symbol in indices_map.items():
        q = fetch_index(name, symbol)
        if q:
            out.append(q)
    return out
