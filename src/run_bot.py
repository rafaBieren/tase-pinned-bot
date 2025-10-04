"""Scheduler entry point for running the Telegram bot during trading hours."""

import asyncio
from contextlib import suppress
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from settings import settings
from main import main as run_bot_main

_WORKING_DAYS = {6, 0, 1, 2, 3}
_START_TIME = time(hour=10, minute=0)
_STOP_TIME = time(hour=18, minute=0)
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


def _is_workday(moment: datetime) -> bool:
    return moment.weekday() in _WORKING_DAYS


def _session_bounds(moment: datetime) -> tuple[datetime, datetime]:
    day = moment.date()
    start = datetime.combine(day, _START_TIME, tzinfo=TZ)
    stop = datetime.combine(day, _STOP_TIME, tzinfo=TZ)
    return start, stop


def _is_within_session(moment: datetime) -> bool:
    if not _is_workday(moment):
        return False
    start, stop = _session_bounds(moment)
    return start <= moment < stop


def _next_session_start(after: datetime) -> datetime:
    for offset in range(0, 8):
        candidate_day = (after + timedelta(days=offset)).date()
        candidate_start = datetime.combine(candidate_day, _START_TIME, tzinfo=TZ)
        if not _is_workday(candidate_start):
            continue
        if candidate_start > after:
            return candidate_start
    raise RuntimeError("Unable to find next session start within 7 days")


async def _sleep_until(target: datetime) -> None:
    while True:
        now = datetime.now(TZ)
        remaining = (target - now).total_seconds()
        if remaining <= 0:
            return
        await asyncio.sleep(min(remaining, _SLEEP_GRANULARITY_SEC))


async def _run_session(stop_at: datetime) -> None:
    stop_label = stop_at.astimezone(TZ).strftime("%Y-%m-%d %H:%M %Z")
    print(f"[INFO] Starting bot updates until {stop_label}")
    bot_task = asyncio.create_task(run_bot_main())
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


async def run_scheduled() -> None:
    print(f"[INFO] Scheduler running in timezone {TZ_NAME}")
    while True:
        now = datetime.now(TZ)
        if _is_within_session(now):
            _, stop_at = _session_bounds(now)
            await _run_session(stop_at)
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
