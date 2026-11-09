import threading
from collections.abc import Callable
from datetime import UTC, date, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from samovar_agent.adapters.demo_session import DemoSessionProvider, DemoSnapshot
from samovar_agent.adapters.urllib_http import UrllibHttpClient
from samovar_agent.domain.errors import UpstreamError
from samovar_agent.engine.duckdb_engine import EngineFactory, EngineLimits
from samovar_agent.engine.parser import SqlParser
from samovar_agent.engine.queries import Queries
from samovar_agent.guard.sql_guard import SqlGuard
from samovar_agent.ports.http import HttpResponse
from samovar_agent.service.data_access import DataAccess
from samovar_agent.service.data_day import DataDay
from tests.fakes.clock import FixedClock
from tests.fakes.demo_snapshot import build_snapshot
from tests.fakes.http import FakeHttpClient
from tests.sql_files import sql

NOON = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


def provider(
    tmp_path: Path, pin: DemoSnapshot, http: FakeHttpClient, now: datetime = NOON, zone: str = "UTC"
) -> DemoSessionProvider:
    return DemoSessionProvider(pin, http, tmp_path / "cache", DataDay(FixedClock(now), zone, zone))


def serve_body(body: bytes) -> Callable[[BaseHTTPRequestHandler], None]:
    def do_get(handler: BaseHTTPRequestHandler) -> None:
        handler.send_response(200)
        handler.end_headers()
        handler.wfile.write(body)

    return do_get


def serving(tmp_path: Path) -> tuple[DemoSnapshot, bytes, FakeHttpClient]:
    pin, body = build_snapshot(tmp_path)
    return pin, body, FakeHttpClient({("GET", pin.url): HttpResponse(200, body)})


def test_the_pinned_snapshot_is_one_file_named_by_its_sha256_over_https() -> None:
    pin = DemoSnapshot.load()
    assert pin.url == f"https://samovar-demo.s3.cloud.ru/mapping/{pin.sha256}.duckdb"
    assert pin.file == pin.sha256 + ".duckdb" and pin.anchor == date(2026, 11, 7)


def test_a_verified_download_is_cached_under_its_sha256_and_not_fetched_again(tmp_path: Path) -> None:
    pin, body, http = serving(tmp_path)
    sessions = provider(tmp_path, pin, http)
    session = sessions.open()
    sessions.open()
    assert len(http.requests) == 1
    assert Path(session.mapping_location) == tmp_path / "cache" / pin.file
    assert (tmp_path / "cache" / pin.file).read_bytes() == body
    assert not list((tmp_path / "cache").glob("*.part"))
    assert session.allowed_directories == (str(tmp_path / "cache") + "/",) and session.extensions == ()
    assert session.s3 is None


def test_a_valid_cache_works_offline(tmp_path: Path) -> None:
    pin, body, http = serving(tmp_path)
    provider(tmp_path, pin, http).open()
    offline = FakeHttpClient()
    provider(tmp_path, pin, offline).open()
    assert offline.requests == []


def test_a_file_with_another_sha256_is_refused_and_nothing_is_kept(tmp_path: Path) -> None:
    pin, body, _ = serving(tmp_path)
    http = FakeHttpClient({("GET", pin.url): HttpResponse(200, body + b"x")})
    with pytest.raises(UpstreamError, match="sha256"):
        provider(tmp_path, pin, http).open()
    assert not (tmp_path / "cache").exists() or list((tmp_path / "cache").iterdir()) == []


def test_a_corrupted_cached_file_is_downloaded_again(tmp_path: Path) -> None:
    pin, body, http = serving(tmp_path)
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / pin.file).write_bytes(b"not the snapshot")
    provider(tmp_path, pin, http).open()
    assert (tmp_path / "cache" / pin.file).read_bytes() == body and len(http.requests) == 1


def test_a_bad_cached_file_is_refused_when_the_download_fails_too(tmp_path: Path) -> None:
    pin, _, _ = serving(tmp_path)
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / pin.file).write_bytes(b"not the snapshot")
    with pytest.raises(UpstreamError, match="update the plugin"):
        provider(tmp_path, pin, FakeHttpClient()).open()


def test_a_missing_snapshot_says_to_update_the_plugin(tmp_path: Path) -> None:
    pin, _, _ = serving(tmp_path)
    with pytest.raises(UpstreamError, match="update the plugin"):
        provider(tmp_path, pin, FakeHttpClient()).open()


def test_a_snapshot_over_the_size_limit_is_refused_through_the_real_client(tmp_path: Path) -> None:
    pin, body, _ = serving(tmp_path)
    server = HTTPServer(("127.0.0.1", 0), type("Big", (BaseHTTPRequestHandler,), {"do_GET": serve_body(body)}))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        local = pin.model_copy(update={"base_url": f"http://127.0.0.1:{server.server_port}/"})
        sessions = DemoSessionProvider(
            local, UrllibHttpClient(5, len(body) - 1), tmp_path / "cache", DataDay(FixedClock(NOON), "UTC", "UTC")
        )
        with pytest.raises(UpstreamError, match="larger than"):
            sessions.open()
    finally:
        server.shutdown()


def test_an_http_error_is_reported_with_its_status(tmp_path: Path) -> None:
    pin, _, _ = serving(tmp_path)
    http = FakeHttpClient({("GET", pin.url): HttpResponse(503, b"")})
    with pytest.raises(UpstreamError, match="HTTP 503"):
        provider(tmp_path, pin, http).open()


@pytest.mark.parametrize(
    ("now", "zone", "days"),
    [
        (datetime(2026, 11, 8, 12, 0, tzinfo=UTC), "UTC", 0),  # yesterday is the snapshot's last day
        (datetime(2026, 11, 20, 12, 0, tzinfo=UTC), "UTC", 12),
        (datetime(2026, 11, 20, 21, 30, tzinfo=UTC), "UTC", 12),  # still the 20th in UTC
        (datetime(2026, 11, 20, 21, 30, tzinfo=UTC), "Europe/Moscow", 13),  # already the 21st in Moscow
    ],
)
def test_the_shift_is_yesterday_in_the_data_timezone_minus_the_anchor(
    tmp_path: Path, now: datetime, zone: str, days: int
) -> None:
    pin, _, http = serving(tmp_path)
    assert provider(tmp_path, pin, http, now, zone).shift_days() == days


def test_the_last_date_of_a_view_is_yesterday_after_the_lock(tmp_path: Path) -> None:
    pin, _, http = serving(tmp_path)
    queries = Queries.load()
    guard = SqlGuard(SqlParser(queries), lambda: date(2026, 11, 20))
    engine = EngineFactory(queries, tmp_path / "ext", EngineLimits("512MB", 1, 5), guard).open(
        provider(tmp_path, pin, http).open()
    )
    try:
        assert engine.query(sql("demo-last-day"), 10).rows == ((date(2026, 11, 19),),)
    finally:
        engine.close()


def test_the_engine_is_reopened_when_the_day_changes_so_the_last_date_stays_yesterday(tmp_path: Path) -> None:
    pin, _, http = serving(tmp_path)
    clock = FixedClock(datetime(2026, 11, 20, 23, 0, tzinfo=UTC))
    day = DataDay(clock, "UTC", "UTC")
    queries = Queries.load()
    guard = SqlGuard(SqlParser(queries), day.today)
    access = DataAccess(
        DemoSessionProvider(pin, http, tmp_path / "cache", day),
        EngineFactory(queries, tmp_path / "ext", EngineLimits("512MB", 1, 5), guard),
        day.today,
    )
    try:
        assert access.engine().query(sql("demo-last-day"), 10).rows == ((date(2026, 11, 19),),)
        assert access.engine() is access.engine()
        clock.current = datetime(2026, 11, 21, 0, 5, tzinfo=UTC)
        assert access.engine().query(sql("demo-last-day"), 10).rows == ((date(2026, 11, 20),),)
    finally:
        access.engine().close()
