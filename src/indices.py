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
from typing import Optional, Iterable, List, Dict, Tuple
import math
import os
import time
from datetime import datetime, timedelta

import requests

# Work around yfinance's optional curl_cffi transport causing attribute errors in some environments
# This MUST be set before any yfinance import
os.environ["YF_USE_CURL_CFFI"] = "false"
os.environ["YF_DISABLE_CURL_CFFI"] = "true"
os.environ["YF_USE_CTX"] = "false"

# Additional workarounds for curl_cffi issues
try:
    import curl_cffi
    # Disable curl_cffi completely if it's causing issues
    os.environ["CURL_CA_BUNDLE"] = ""
except ImportError:
    pass

from loguru import logger
import yfinance as yf

# Import alternative data source with error handling
try:
    from .alternative_data_source import get_index_data_from_alternative_source
except ImportError:
    # Fallback if alternative_data_source is not available
    def get_index_data_from_alternative_source(name: str):
        return None

# Simple in-memory cache with TTL
_cache: Dict[str, Tuple[IndexQuote, float]] = {}
CACHE_TTL = 300  # 5 minutes

ALT_SYMBOLS = {
    # If the primary symbol fails, try alternatives in order
    "TA35.TA": ["^TA35.TA", "TA35"], # "TA35-IND.TA"
    "TA125.TA": ["^TA125.TA", "TA125"], # "TA125-IND.TA"
    "TA90.TA": ["^TA90.TA", "TA90"], # "TA90-IND.TA"
    "TA-BANKS.TA": ["^TA-BANKS.TA", "BANKS.TA", "^BANKS.TA"],
}


SPARK_URL = "https://query1.finance.yahoo.com/v7/finance/spark"
_SPARK_DEFAULT_PARAMS = {"range": "1d", "interval": "1m"}
_SPARK_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}
_SPARK_TIMEOUT = 10.0


def _fetch_spark_batch(symbols: Iterable[str]) -> Dict[str, Dict[str, float]]:
    '''Fetch last price and previous close for a batch of tickers via Yahoo spark API.'''
    tickers = sorted({s.strip() for s in symbols if s})
    if not tickers:
        return {}

    params = dict(_SPARK_DEFAULT_PARAMS)
    params["symbols"] = ",".join(tickers)

    try:
        response = requests.get(
            SPARK_URL,
            params=params,
            headers=_SPARK_HEADERS,
            timeout=_SPARK_TIMEOUT,
        )
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - we want to log any failure here
        logger.warning(f"Yahoo spark request failed: {exc}")
        return {}

    try:
        payload = response.json()
    except ValueError as exc:
        logger.warning(f"Failed to decode Yahoo spark response: {exc}")
        return {}

    results: Dict[str, Dict[str, float]] = {}
    for item in payload.get("spark", {}).get("result", []):
        symbol = item.get("symbol")
        responses = item.get("response") or []
        if not symbol or not responses:
            continue

        meta = responses[0].get("meta") or {}
        price = meta.get("regularMarketPrice")
        prev_close = meta.get("previousClose") or meta.get("chartPreviousClose")
        market_time = meta.get("regularMarketTime")

        if price is None or prev_close is None or market_time is None:
            continue

        results[symbol] = {
            "price": float(price),
            "prev_close": float(prev_close),
            "timestamp": int(market_time),
        }

    missing = sorted(set(tickers) - set(results))
    if missing:
        logger.debug(f"Yahoo spark missing data for: {missing}")

    return results


def _get_cached_data(cache_key: str) -> Optional[IndexQuote]:
    """Get data from cache if it's still valid."""
    if cache_key in _cache:
        quote, timestamp = _cache[cache_key]
        if time.time() - timestamp < CACHE_TTL:
            logger.info(f"Using cached data for {cache_key}")
            return quote
        else:
            # Remove expired entry
            del _cache[cache_key]
    return None


def _cache_data(cache_key: str, quote: IndexQuote) -> None:
    """Cache the data with current timestamp."""
    _cache[cache_key] = (quote, time.time())
    logger.info(f"Cached data for {cache_key}")


class IndexQuote:
    """In-memory representation of a single index quote and its derived fields."""

    def __init__(self, name: str, symbol: str, price: float, prev_close: float, price_date: Optional[datetime] = None):
        self.name = name
        self.symbol = symbol
        self.price = float(price)
        self.prev_close = float(prev_close)
        self.price_date = price_date

    @property
    def change_pct(self) -> float:
        """Daily percentage change vs previous close."""
        if self.prev_close and not math.isclose(self.prev_close, 0.0):
            return (self.price / self.prev_close - 1.0) * 100.0
        return 0.0


def _try_get_prev_close(symbol: str) -> Optional[float]:
    """Fetch previous close from recent daily candles with retry logic."""
    import random

    max_retries = 2
    base_delay = 1.0

    for attempt in range(max_retries):
        try:
            hist = yf.download(
                symbol,
                period="7d",
                interval="1d",
                progress=False,
                auto_adjust=False,
            )
            if hist is None or hist.empty:
                logger.warning(f"No historical data available for {symbol}")
                return None

            closes = hist["Close"]
            if getattr(closes, "ndim", 1) > 1:
                closes = closes.iloc[:, 0]
            closes = closes.dropna()

            if closes.empty:
                logger.warning(f"No close prices found for {symbol}")
                return None

            if len(closes) >= 2:
                return float(closes.iloc[-2])
            return float(closes.iloc[-1])
        except Exception as exc:
            if attempt < max_retries - 1:
                delay = base_delay + random.uniform(0, 0.5)
                logger.warning(f"Failed to get {symbol} prev close (attempt {attempt + 1}): {exc}. Retrying in {delay:.1f}s...")
                time.sleep(delay)
            else:
                logger.warning(f"Failed to get {symbol} prev close after {max_retries} attempts: {exc}")
                return None
    return None


def _try_get_last_price(symbol: str) -> Optional[Tuple[float, datetime]]:
    """Fetch the latest intraday close price with retry logic."""
    import random

    max_retries = 2
    base_delay = 1.0

    for period, interval in [("1d", "1m"), ("5d", "5m")]:
        for attempt in range(max_retries):
            try:
                hist = yf.download(
                    symbol,
                    period=period,
                    interval=interval,
                    progress=False,
                    auto_adjust=False,
                )
                if hist is None or hist.empty:
                    logger.debug(f"No intraday data returned for {symbol} at {period}/{interval}")
                    break

                closes = hist["Close"]
                if getattr(closes, "ndim", 1) > 1:
                    closes = closes.iloc[:, 0]
                closes = closes.dropna()

                if closes.empty:
                    logger.debug(f"Close series empty for {symbol} at {period}/{interval}")
                    break

                last_price = float(closes.iloc[-1])
                last_timestamp = closes.index[-1]
                # last_timestamp can be pd.Timestamp; convert to python datetime
                last_dt = last_timestamp.to_pydatetime()
                return last_price, last_dt
            except Exception as exc:
                if attempt < max_retries - 1:
                    delay = base_delay + random.uniform(0, 0.5)
                    logger.warning(f"Failed to get {symbol} data for {period}/{interval} (attempt {attempt + 1}): {exc}. Retrying in {delay:.1f}s...")
                    time.sleep(delay)
                else:
                    logger.warning(f"Failed to get {symbol} data for {period}/{interval} after {max_retries} attempts: {exc}")
                    break

    # Fallback to fast_info if available
    for attempt in range(max_retries):
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            last = getattr(info, "last_price", None) or getattr(info, "lastPrice", None) or info.get("last_price", None)
            if last is not None:
                # fast_info does not provide a reliable timestamp, so we don't return one
                return float(last), None
        except Exception as exc:
            if attempt < max_retries - 1:
                delay = base_delay + random.uniform(0, 0.5)
                logger.warning(f"Failed to get {symbol} fast_info (attempt {attempt + 1}): {exc}. Retrying in {delay:.1f}s...")
                time.sleep(delay)
            else:
                logger.warning(f"Failed to get {symbol} fast_info after {max_retries} attempts: {exc}")
                break

    return None


def fetch_index(name: str, symbol: str, spark_data: Optional[Dict[str, Dict[str, float]]] = None) -> Optional[IndexQuote]:
    """
    Fetch last price and previous close for one index.
    If primary symbol fails, try alternative symbols if configured.
    Uses caching to reduce API calls.
    """
    cache_key = f"{name}_{symbol}"
    cached_data = _get_cached_data(cache_key)
    if cached_data:
        return cached_data

    symbols_to_try = [symbol]
    if symbol in ALT_SYMBOLS:
        symbols_to_try.extend(ALT_SYMBOLS[symbol])

    spark_data = spark_data or {}

    for attempt_symbol in symbols_to_try:
        logger.info(f"Attempting to fetch data for {name} using symbol: {attempt_symbol}")

        price: Optional[float] = None
        prev_close: Optional[float] = None
        price_date: Optional[datetime] = None

        data_point = spark_data.get(attempt_symbol)
        if data_point:
            price = data_point.get("price")
            prev_close = data_point.get("prev_close")
            timestamp = data_point.get("timestamp")
            if price is not None and prev_close is not None and timestamp is not None:
                logger.info(f"Using Yahoo spark data for {name} ({attempt_symbol})")
                price_date = datetime.fromtimestamp(int(timestamp))

        if price is None:
            price_info = _try_get_last_price(attempt_symbol)
            if price_info:
                price, price_date = price_info

        if price is None:
            logger.warning(f"Failed to get last price for {attempt_symbol}")
            continue

        if prev_close is None:
            prev_close = _try_get_prev_close(attempt_symbol)
        if prev_close is None:
            logger.warning(f"Failed to get previous close for {attempt_symbol}")
            continue

        logger.info(f"Successfully fetched data for {name} using symbol: {attempt_symbol}")
        quote = IndexQuote(
            name=name,
            symbol=attempt_symbol,
            price=price,
            prev_close=prev_close,
            price_date=price_date,
        )
        _cache_data(cache_key, quote)
        return quote

    logger.error(f"Failed to fetch data for {name} with all attempted symbols: {symbols_to_try}")
    logger.info(f"Trying alternative data source for {name}")

    try:
        alt_data = get_index_data_from_alternative_source(name)
        if alt_data:
            quote = IndexQuote(
                name=name,
                symbol=symbol,
                price=alt_data['price'],
                prev_close=alt_data['prev_close']
                # price_date is not available from this source
            )
            logger.info(f"Successfully fetched {name} from alternative source")
            _cache_data(cache_key, quote)
            return quote
    except Exception as e:  # noqa: BLE001 - we deliberately log any failure
        logger.warning(f"Alternative data source also failed for {name}: {e}")

    return None


def fetch_all(indices_map: dict[str, str]) -> List[IndexQuote]:
    """Fetch all indices defined in the configuration with respectful delays."""
    out: List[IndexQuote] = []

    symbols_to_prefetch = set(indices_map.values())
    for sym in indices_map.values():
        symbols_to_prefetch.update(ALT_SYMBOLS.get(sym, []))

    spark_data = _fetch_spark_batch(symbols_to_prefetch)
    if spark_data:
        logger.info(f"Prefetched Yahoo spark data for {len(spark_data)} symbols")
    else:
        logger.warning("Yahoo spark prefetch returned no data; falling back to yfinance per symbol")

    items = list(indices_map.items())
    for idx, (name, symbol) in enumerate(items):
        candidate_symbols = [symbol] + ALT_SYMBOLS.get(symbol, [])
        spark_available = any(spark_data.get(sym) for sym in candidate_symbols)

        quote = fetch_index(name, symbol, spark_data=spark_data)
        if quote:
            out.append(quote)

        if idx < len(items) - 1 and not spark_available:
            logger.info("Waiting 1 second before next request to respect rate limiting when using yfinance fallback...")
            time.sleep(1)

    return out

