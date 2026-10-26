"""Time on the line. A real station uses the wall clock; the emulated line advances a clock per slot by the
modelled duration of each step, so a shift of hundreds of airframes runs in minutes but its KPIs read in real
minutes."""

from __future__ import annotations

import datetime as dt
from typing import Protocol


class Clock(Protocol):
    def now(self) -> dt.datetime: ...
    def spend(self, seconds: float) -> None: ...


class WallClock:
    def now(self) -> dt.datetime:
        return dt.datetime.now(dt.UTC)

    def spend(self, seconds: float) -> None:
        pass  # the time was really spent


class SimClock:
    def __init__(self, start: dt.datetime) -> None:
        self.t = start

    def now(self) -> dt.datetime:
        return self.t

    def spend(self, seconds: float) -> None:
        self.t += dt.timedelta(seconds=seconds)
