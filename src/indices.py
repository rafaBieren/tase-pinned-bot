"""
indices.py
----------
Batch data-fetching and basic transformation for TASE index quotes.

Hardening against Yahoo Finance rate-limits:
- Use ONE shared requests.Session with a browser-like User-Agent.
- Configure HTTP retries (429/5xx) via urllib3 Retry + exponential backoff.
- Perform *two* batched downloads (daily & intraday) with threads=False.
- Add an explicit backoff+jitter retry around each batch call.
- Fall back to alternative symbols in a *single* extra batch.

Public API
==========
- class IndexQuote
- fetch_all(indices_map: dict[str, str]) -> list[IndexQuote]
"""

from __future__ import annotations

from typing import Optional, List, Dict
import math
import random
import time

import pandas as pd
import yfinance as yf
from loguru import logger

# --- Optional import of yfinance rate-limit exception (fallback if missing) ---
try:
    from yfinance.exceptions import YFRateLimitError
except Exception:  # pragma: no cover
    class YFRateLimitError(Exception):
        """Fallback when the real exception is unavailable."""
        pass

# --- HTTP session with retries (works only when yfinance uses requests) ---
import requests
from requests.adapters import HTTPAdapter
try:
    # urllib3 location differs across versions
    from urllib3.util.retry import Retry  # type: ignore
except Exception:  # pragma: no cover
    Retry = None  # minimal fallback; we still use manual backoff around downloads.

# If the primary symbol fails, try these alternatives (in order).
ALT_SYMBOLS: Dict[str, list[str]] = {
    "^TA125.TA": ["TA125.TA", "^TA100"],
    "TA125.TA": ["^TA125.TA", "^TA100"],
}

# A single global session reused across calls.
_SESSION: Optional[requests.Session] = None


def _get_session() -> Optional[requests.Session]:
    """
    Build (once) and return a shared requests.Session:
    - Browser-like User-Agent to reduce anti-bot triggers.
    - HTTP retries for 429 and common 5xx.
    - Small connection pool to keep the footprint modest.
    """
    global _SESSION
    if _SESSION is not None:
        return _SESSION

    try:
        s = requests.Session()
        s.headers.update({
            # A common, modern desktop UA string:
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        })

        if Retry is not None:
            retry = Retry(
                total=3,                # up to 3 retries
                connect=3,
                read=3,
                status=3,
                backoff_factor=0.8,     # 0.8, 1.6, 3.2 seconds...
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset(["GET", "POST"]),
                raise_on_status=False,
                respect_retry_after_header=True,
            )
            adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=8)
            s.mount("https://", adapter)
            s.mount("http://", adapter)

        _SESSION = s
        return _SESSION
    except Exception as e:  # extremely defensive
        logger.warning(f"Failed to create shared HTTP session; continuing without it: {e}")
        return None


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

    def __repr__(self) -> str:
        return f"IndexQuote(name={self.name!r}, symbol={self.symbol!r}, price={self.price:.2f}, prev_close={self.prev_close:.2f})"


# ---------- Small utilities ----------

def _as_float(x) -> float:
    """
    Convert a pandas/numpy scalar or a 1-element Series to float safely.

    Why? yfinance sometimes returns 1-element Series; calling float() directly
    on a Series is deprecated. This helper extracts the underlying scalar.
    """
    try:
        return float(x)
    except TypeError:
        try:
            return float(x.iloc[0])
        except Exception:
            try:
                return float(x.item())
            except Exception:
                return float(getattr(x, "squeeze", lambda: x)())


def _extract_close_series(df: Optional[pd.DataFrame], symbol: str) -> Optional[pd.Series]:
    """
    Given a batched yfinance DataFrame (possibly MultiIndex columns),
    try to extract the 'Close' Series for a specific symbol.

    Supports both shapes:
    - MultiIndex columns: df[(symbol, 'Close')]
    - group_by='ticker' layout: df[symbol]['Close']
    - Single-ticker layout: df['Close']
    """
    if df is None or getattr(df, "empty", True):
        return None

    try:
        if isinstance(df.columns, pd.MultiIndex) and (symbol, "Close") in df.columns:
            return df[(symbol, "Close")]
    except Exception:
        pass

    try:
        if symbol in df.columns:
            sub = df[symbol]
            if isinstance(sub, pd.DataFrame) and "Close" in sub.columns:
                return sub["Close"]
    except Exception:
        pass

    try:
        if "Close" in df.columns and isinstance(df["Close"], pd.Series):
            return df["Close"]
    except Exception:
        pass

    return None


def _download_batch_once(
    tickers: list[str],
    *,
    period: str,
    interval: str,
    session: Optional[requests.Session],
) -> Optional[pd.DataFrame]:
    """
    Single attempt to download a batch via yfinance.

    Important flags:
    - auto_adjust=False  : use raw closes for consistent prev/last comparison.
    - group_by='ticker'  : keeps per-symbol separation in columns.
    - threads=False      : avoids bursts of parallel requests.
    - session            : pass our shared Session if available.
    """
    if not tickers:
        return None

    try:
        df = yf.download(
            tickers=tickers,
            period=period,
            interval=interval,
            auto_adjust=False,
            progress=False,
            group_by="ticker",
            threads=False,
            session=session,
        )
        return df
    except YFRateLimitError as e:
        logger.error(f"Rate-limited ({period}, {interval}) on {tickers}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Batch download failed ({period}, {interval}): {e}")
        return None


def _download_batch_with_backoff(
    tickers: list[str],
    *,
    period: str,
    interval: str,
    max_attempts: int = 2,
) -> Optional[pd.DataFrame]:
    """
    Download a batch with explicit exponential backoff + jitter around yfinance.download.

    Why this layer if we already configured HTTP retries?
    - HTTP retries handle network-level errors and 429/5xx that bubble up from requests.
    - Yahoo may still throttle at the application layer; retrying the *whole call* with
      a small randomized delay often succeeds.
    """
    session = _get_session()
    attempt = 0
    backoff = 1.0  # seconds

    while attempt < max_attempts:
        attempt += 1
        df = _download_batch_once(tickers, period=period, interval=interval, session=session)
        if df is not None and not getattr(df, "empty", True):
            return df

        if attempt < max_attempts:
            # jittered exponential backoff
            delay = backoff * (1.0 + random.random())  # [backoff, 2*backoff)
            logger.warning(f"Retrying batch ({period}, {interval}) in {delay:.1f}s ...")
            time.sleep(delay)
            backoff *= 2.0

    return None


# ---------- Core: batched fetch ----------

def fetch_all(indices_map: Dict[str, str]) -> List[IndexQuote]:
    """
    Fetch last price and previous close for all indices in ONE go to reduce
    Yahoo rate-limit issues.

    Parameters
    ----------
    indices_map : dict[str, str]
        Mapping from display name -> Yahoo symbol (e.g., {"TA-35": "TA35.TA", ...})

    Returns
    -------
    list[IndexQuote]
        Quotes with computed change percentage. Entries with insufficient data
        are skipped. Order matches the input mapping.
    """
    out: List[IndexQuote] = []
    if not indices_map:
        return out

    # Keep a stable order from the mapping
    items: list[tuple[str, str]] = list(indices_map.items())
    tickers: list[str] = [symbol for _, symbol in items]

    # 1) Two batched calls: daily for prev_close, intraday for last
    #    (with explicit backoff around each call)
    daily_df = _download_batch_with_backoff(tickers, period="7d", interval="1d")
    intra_df = _download_batch_with_backoff(tickers, period="1d", interval="1m")

    # Build quick-access dicts for prev/last per *original* symbol
    prev_by_symbol: Dict[str, Optional[float]] = {s: None for s in tickers}
    last_by_symbol: Dict[str, Optional[float]] = {s: None for s in tickers}

    for symbol in tickers:
        # previous close
        try:
            dclose = _extract_close_series(daily_df, symbol)
            if dclose is not None and len(dclose) >= 2:
                prev_by_symbol[symbol] = _as_float(dclose.iloc[-2])
            elif dclose is not None and len(dclose) == 1:
                prev_by_symbol[symbol] = _as_float(dclose.iloc[-1])
        except Exception:
            pass

        # last price (latest intraday close)
        try:
            iclose = _extract_close_series(intra_df, symbol)
            if iclose is not None and len(iclose) >= 1:
                last_by_symbol[symbol] = _as_float(iclose.iloc[-1])
        except Exception:
            pass

    # 2) For symbols with missing data, try ALT_SYMBOLS in a single extra batch
    missing_symbols = [s for s in tickers if prev_by_symbol[s] is None or last_by_symbol[s] is None]
    alt_pool: list[str] = []
    for sym in missing_symbols:
        alt_pool.extend(ALT_SYMBOLS.get(sym, []))
    # Remove duplicates while preserving order
    seen = set()
    alt_batch = [x for x in alt_pool if not (x in seen or seen.add(x))]

    daily_alt = _download_batch_with_backoff(alt_batch, period="7d", interval="1d") if alt_batch else None
    intra_alt = _download_batch_with_backoff(alt_batch, period="1d", interval="1m") if alt_batch else None

    # Fill missing using alternatives
    chosen_symbol_for: Dict[str, str] = {s: s for s in tickers}
    for sym in missing_symbols:
        for alt in ALT_SYMBOLS.get(sym, []):
            # fill prev if missing
            if prev_by_symbol[sym] is None:
                try:
                    dclose = _extract_close_series(daily_alt, alt)
                    if dclose is not None:
                        if len(dclose) >= 2:
                            prev_by_symbol[sym] = _as_float(dclose.iloc[-2])
                        elif len(dclose) == 1:
                            prev_by_symbol[sym] = _as_float(dclose.iloc[-1])
                except Exception:
                    pass

            # fill last if missing
            if last_by_symbol[sym] is None:
                try:
                    iclose = _extract_close_series(intra_alt, alt)
                    if iclose is not None and len(iclose) >= 1:
                        last_by_symbol[sym] = _as_float(iclose.iloc[-1])
                except Exception:
                    pass

            if prev_by_symbol[sym] is not None and last_by_symbol[sym] is not None:
                chosen_symbol_for[sym] = alt
                logger.warning(f"Using alternative symbol for {sym} -> {alt}")
                break

    # 3) Build IndexQuote objects in the original order
    for name, orig_symbol in items:
        prev = prev_by_symbol.get(orig_symbol)
        last = last_by_symbol.get(orig_symbol)
        eff_symbol = chosen_symbol_for.get(orig_symbol, orig_symbol)

        if prev is None or last is None:
            logger.error(f"Failed fetching {name} ({orig_symbol})")
            continue

        out.append(IndexQuote(name=name, symbol=eff_symbol, price=last, prev_close=prev))

    return out
