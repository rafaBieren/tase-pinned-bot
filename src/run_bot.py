"""Scheduler entry point for running the Telegram bot during trading hours."""

import asyncio
from contextlib import suppress
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, Tuple

from settings import settings
from main import main as run_bot_main
from tase_calendar import get_trading_hours

_SLEEP_GRANULARITY_SEC = 60.0


def _resolve_timezone() -> ZoneInfo:
    tz_name = (settings.tz or "Asia/Jerusalem").strip()
    try:
        return ZoneInfo(tz_name)
    except Exception:
        fallback = "Asia/Jerusalem"
        print(f"[WARN] Could not load timezone '{tz_name}', falling back to '{fallback}'.")
        return ZoneInfo(fallback)


TZ = _resolve_timezone()
TZ_NAME = getattr(TZ, "key", str(TZ))


def _session_bounds(moment: datetime) -> Optional[Tuple[datetime, datetime]]:
    """Get the trading session start and end for a given datetime."""
    hours = get_trading_hours(moment)
    if not hours:
        return None
    
    start_time, stop_time = hours
    day = moment.date()
    start = datetime.combine(day, start_time, tzinfo=TZ)
    stop = datetime.combine(day, stop_time, tzinfo=TZ)
    return start, stop


def _is_within_session(moment: datetime) -> bool:
    """Check if the current moment is within a trading session."""
    bounds = _session_bounds(moment)
    if not bounds:
        return False
    start, stop = bounds
    return start <= moment < stop


async def _sleep_until(target: datetime) -> None:
    """Sleep until a target datetime is reached."""
    while True:
        now = datetime.now(TZ)
        remaining = (target - now).total_seconds()
        if remaining <= 0:
            return
        await asyncio.sleep(min(remaining, _SLEEP_GRANULARITY_SEC))


async def _run_session(stop_at: datetime) -> None:
    stop_label = stop_at.astimezone(TZ).strftime("%Y-%m-%d %H:%M %Z")
    print(f"[INFO] Starting bot updates until {stop_label}")
    bot_task = asyncio.create_task(run_bot_main(run_once=False, market_open=True))
    try:
        remaining = max(0.0, (stop_at - datetime.now(TZ)).total_seconds())
        await asyncio.wait_for(bot_task, timeout=remaining)
    except asyncio.TimeoutError:
        print("[INFO] Trading window ended; stopping bot task.")
        bot_task.cancel()
        with suppress(asyncio.CancelledError):
            await bot_task
    except Exception:
        bot_task.cancel()
        with suppress(asyncio.CancelledError):
            await bot_task
        raise
    else:
        try:
            bot_task.result()
        except Exception:
            raise
        raise SystemExit("[ERROR] Bot task finished before the scheduled stop time. See logs above.")


def _next_session_start(after: datetime) -> datetime:
    """Find the start of the next trading session."""
    for offset in range(0, 8):
        candidate_day = (after + timedelta(days=offset)).date()
        # Check at noon to be safe with timezones
        candidate_moment = datetime.combine(candidate_day, time(12, 0), tzinfo=TZ)
        
        bounds = _session_bounds(candidate_moment)
        if not bounds:
            continue
        
        candidate_start, _ = bounds
        if candidate_start > after:
            return candidate_start
            
    raise RuntimeError("Unable to find next session start within 7 days")


async def run_scheduled() -> None:
    print(f"[INFO] Scheduler running in timezone {TZ_NAME}")
    off_session_message_sent = False
    while True:
        now = datetime.now(TZ)
        if _is_within_session(now):
            off_session_message_sent = False  # Reset for next off-session period
            _, stop_at = _session_bounds(now)
            await _run_session(stop_at)
            continue

        if not off_session_message_sent:
            print("[INFO] Outside of trading hours. Sending final update.")
            try:
                await run_bot_main(run_once=True, market_open=False)
                off_session_message_sent = True
                print("[INFO] Final update sent. Waiting for next session.")
            except Exception as exc:
                print(f"[ERROR] Failed to send off-session message: {exc}")
                # Don't set flag, retry on next check after a delay
                await asyncio.sleep(_SLEEP_GRANULARITY_SEC)
                continue

        next_start = _next_session_start(now)
        start_label = next_start.strftime("%Y-%m-%d %H:%M %Z")
        print(f"[INFO] Waiting until {start_label} to start updates.")
        await _sleep_until(next_start)


if __name__ == "__main__":
    try:
        asyncio.run(run_scheduled())
    except KeyboardInterrupt:
        print("[INFO] Scheduler stopped by user.")
