"""Accelerated simulation clock on East Africa Time (naive datetimes)."""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

EAT = timezone(timedelta(hours=3))


def default_sim_start(start_hour: float, today: date | None = None) -> datetime:
    today = today or datetime.now(EAT).date()
    return datetime.combine(today, datetime.min.time()) + timedelta(hours=start_hour)


class SimClock:
    def __init__(self, start: datetime, speed: float, time_fn: Callable[[], float] = time.monotonic):
        self._lock = threading.Lock()
        self._time_fn = time_fn
        self._sim_anchor = start
        self._real_anchor = time_fn()
        self._speed = speed

    @property
    def speed(self) -> float:
        return self._speed

    def now(self) -> datetime:
        with self._lock:
            return self._now_unlocked()

    def _now_unlocked(self) -> datetime:
        elapsed = self._time_fn() - self._real_anchor
        return self._sim_anchor + timedelta(seconds=elapsed * self._speed)

    def _reanchor(self, sim_now: datetime) -> None:
        self._sim_anchor = sim_now
        self._real_anchor = self._time_fn()

    def set_speed(self, speed: float) -> None:
        with self._lock:
            self._reanchor(self._now_unlocked())
            self._speed = speed

    def jump_to_hour(self, hour: float) -> datetime:
        """Move forward to the next occurrence of `hour` (never backwards)."""
        with self._lock:
            now = self._now_unlocked()
            target = datetime.combine(now.date(), datetime.min.time()) + timedelta(hours=hour)
            if target <= now:
                target += timedelta(days=1)
            self._reanchor(target)
            return target

    def advance(self, delta: timedelta) -> datetime:
        if delta < timedelta(0):
            raise ValueError("the sim clock only moves forward")
        with self._lock:
            target = self._now_unlocked() + delta
            self._reanchor(target)
            return target
