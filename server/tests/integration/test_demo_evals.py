"""Reference SQL of the demo questions (`evals/demo.json`) against the real demo snapshot, when it is on this machine.

The snapshot is the file the plugin downloads (see `demo-snapshot.json`); set SAMOVAR_DEMO_SNAPSHOT to its local path.
There is no network call: a scripted HttpClient serves the file to the real DemoSessionProvider, whose clock is set so
that the date shift is zero (today = anchor + 1 day), which keeps the DATE literals of the SQL files valid.
"""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from samovar_agent.adapters.demo_session import DemoSessionProvider, DemoSnapshot
from samovar_agent.domain.catalog import Catalog, LayerId
from samovar_agent.domain.values import json_value
from samovar_agent.engine.duckdb_engine import EngineFactory, EngineLimits
from samovar_agent.engine.parser import SqlParser
from samovar_agent.engine.queries import Queries
from samovar_agent.guard.sql_guard import GuardPolicy, SqlGuard
from samovar_agent.ports.http import HttpResponse
from samovar_agent.service.data_day import DataDay
from samovar_agent.settings import Limits
from tests.conftest import REPO
from tests.fakes.clock import FixedClock
from tests.fakes.http import FakeHttpClient
from tests.sql_files import sql

SNAPSHOT_PATH = os.environ.get("SAMOVAR_DEMO_SNAPSHOT")
EVALS = REPO / "evals" / "demo.json"

pytestmark = pytest.mark.skipif(not SNAPSHOT_PATH, reason="SAMOVAR_DEMO_SNAPSHOT is not set")


def rows_of(engine_rows: tuple[tuple[object, ...], ...]) -> list[list[object]]:
    return [[round(v, 6) if isinstance(v, float) else v for v in (json_value(x) for x in row)] for row in engine_rows]


def test_every_demo_question_answers_as_recorded(catalog: Catalog, tmp_path: Path) -> None:
    assert SNAPSHOT_PATH is not None
    pin = DemoSnapshot.load()
    http = FakeHttpClient({("GET", pin.url): HttpResponse(200, Path(SNAPSHOT_PATH).read_bytes())})
    document = json.loads(EVALS.read_text(encoding="utf-8"))
    today = datetime.fromisoformat(document["today"]).replace(tzinfo=UTC) + timedelta(hours=12)
    provider = DemoSessionProvider(pin, http, tmp_path / "demo", DataDay(FixedClock(today), "UTC", "UTC"))
    queries = Queries.load()
    guard = SqlGuard(SqlParser(queries), lambda: today.date())
    policy = GuardPolicy(
        window_days=Limits().dds_window_days,
        date_columns={t.view: t.date_column for t in catalog.tables if t.layer is LayerId.DDS and t.date_column},
        views=catalog.views(),
    )
    engine = EngineFactory(queries, tmp_path / "ext", EngineLimits("1GB", 2, 30), guard).open(provider.open())
    try:
        for item in document["questions"]:
            accepted = guard.check((REPO / "evals" / item["sql"]).read_text(encoding="utf-8"), policy)
            raw = engine.query(accepted.sql, 500)
            assert item["expected"] == {
                "columns": [name for name, _ in raw.columns],
                "rows": rows_of(raw.rows),
            }, item["id"]
    finally:
        engine.close()


def test_demo_dates_end_yesterday_on_the_real_snapshot(catalog: Catalog, tmp_path: Path) -> None:
    assert SNAPSHOT_PATH is not None
    pin = DemoSnapshot.load()
    http = FakeHttpClient({("GET", pin.url): HttpResponse(200, Path(SNAPSHOT_PATH).read_bytes())})
    now = datetime(2027, 3, 1, 12, 0, tzinfo=UTC)
    provider = DemoSessionProvider(pin, http, tmp_path / "demo", DataDay(FixedClock(now), "UTC", "UTC"))
    queries = Queries.load()
    guard = SqlGuard(SqlParser(queries), lambda: now.date())
    engine = EngineFactory(queries, tmp_path / "ext", EngineLimits("1GB", 2, 30), guard).open(provider.open())
    try:
        raw = engine.query(sql("demo-last-day-traffic"), 1)
    finally:
        engine.close()
    assert [json_value(v) for v in raw.rows[0]] == ["2027-02-28"]
