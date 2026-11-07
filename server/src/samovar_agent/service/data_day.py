"""Which calendar day is "today" for the data, and in which timezone.

The catalog fixes no timezone: each source's day (`dt`) is in its own zone (the Metrika counter's, the amoCRM
account's; see each table's day_rule). "Today" is taken in `SAMOVAR_TIMEZONE` when set, else in the default zone.
A zone the system does not know (Windows without tzdata) falls back to UTC and is reported as a problem.
"""

from dataclasses import dataclass
from datetime import UTC, date, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from samovar_agent.ports.clock import Clock

UTC_NAME = "UTC"


@dataclass(frozen=True)
class DayZone:
    name: str
    zone: tzinfo
    problems: tuple[str, ...] = ()


def zone_named(name: str) -> DayZone:
    if name == UTC_NAME:
        return DayZone(UTC_NAME, UTC)
    try:
        return DayZone(name, ZoneInfo(name))
    except (ZoneInfoNotFoundError, ValueError):
        return DayZone(UTC_NAME, UTC, (f"Timezone {name} is unavailable on this system: dates use UTC.",))


class DataDay:
    def __init__(self, clock: Clock, override: str | None, default: str) -> None:
        self._clock = clock
        self._name = override or default

    def zone(self) -> DayZone:
        return zone_named(self._name)

    def today(self) -> date:
        return self._clock.now().astimezone(self.zone().zone).date()
