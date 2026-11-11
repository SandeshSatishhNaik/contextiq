"""Context engine: decides which account is active and what matters right now, without asking.

Signals (all optional, in this order of trust): the user's setup choices, local time and weekday,
and — only if the user allowed it — distance from home. Nothing here is stored except the home point
the user explicitly set in setup.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .models import User

TRAVEL_KM = 100


def _km(a_lat, a_lon, b_lat, b_lon) -> float:
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


@dataclass
class Ctx:
    account: str  # personal | business
    reason: str
    part: str  # morning | afternoon | evening | night
    weekend: bool
    travel: bool
    km_from_home: float | None
    local_hour: int

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def part_of_day(h: int) -> str:
    return "morning" if 5 <= h < 12 else "afternoon" if h < 17 else "evening" if h < 22 else "night"


def decide(user: User, local_hour: int, weekday: int, lat: float | None = None, lon: float | None = None,
           override: str | None = None) -> Ctx:
    part, weekend = part_of_day(local_hour), weekday >= 5
    km = None
    if user.location_ok and lat is not None and lon is not None and user.home_lat is not None:
        km = round(_km(user.home_lat, user.home_lon, lat, lon), 1)
    travel = km is not None and km > TRAVEL_KM
    if override in ("personal", "business"):
        return Ctx(override, "you switched", part, weekend, travel, km, local_hour)
    if user.uses in ("personal", "business"):
        return Ctx(user.uses, "your only account", part, weekend, travel, km, local_hour)
    at_work_time = not weekend and user.work_start_hour <= local_hour < user.work_end_hour
    if travel:
        return Ctx("personal", "you're travelling", part, weekend, travel, km, local_hour)
    if at_work_time:
        return Ctx("business", "work hours", part, weekend, travel, km, local_hour)
    return Ctx("personal", "weekend" if weekend else "after work" if local_hour >= user.work_end_hour else "before work",
               part, weekend, travel, km, local_hour)
