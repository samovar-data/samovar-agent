from datetime import UTC, datetime

from samovar_agent.service.data_day import DataDay
from tests.fakes.clock import FixedClock

# 21:30 UTC is already the next day in Moscow and Yekaterinburg, still the same day in UTC.
CLOCK = FixedClock(datetime(2026, 10, 21, 21, 30, tzinfo=UTC))


def test_without_a_setting_the_default_zone_is_used() -> None:
    day = DataDay(CLOCK, None, "Europe/Moscow")
    assert day.zone().name == "Europe/Moscow" and day.zone().problems == ()
    assert str(day.today()) == "2026-10-22"


def test_the_setting_overrides_the_default_zone() -> None:
    assert DataDay(CLOCK, "Asia/Yekaterinburg", "Europe/Moscow").zone().name == "Asia/Yekaterinburg"
    assert str(DataDay(CLOCK, "UTC", "Europe/Moscow").today()) == "2026-10-21"


def test_an_unknown_zone_falls_back_to_utc_with_a_problem() -> None:
    zone = DataDay(CLOCK, "Mars/Olympus", "Europe/Moscow").zone()
    assert zone.name == "UTC" and "unavailable" in zone.problems[0]
