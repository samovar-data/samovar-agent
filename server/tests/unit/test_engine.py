from datetime import date
from pathlib import Path

import pytest

from samovar_agent.adapters.fixture_session import FixtureSessionProvider
from samovar_agent.domain.errors import (
    AccessDenied,
    LockdownError,
    NoDataYet,
    QueryFailed,
    QueryRejected,
    QueryTimeout,
    UpstreamError,
)
from samovar_agent.domain.session import DataSession
from samovar_agent.engine.duckdb_engine import Engine, EngineFactory, EngineLimits, storage_failure
from samovar_agent.engine.parser import SqlParser
from samovar_agent.engine.queries import Queries
from samovar_agent.engine.settings import Resolved, assert_bootstrap
from samovar_agent.engine.sql_template import Literal, render
from samovar_agent.guard.sql_guard import SqlGuard
from tests.sql_files import sql

LIMITS = EngineLimits(memory_limit="512MB", threads=1, timeout_seconds=5)


def factory(tmp_path: Path, limits: EngineLimits = LIMITS) -> EngineFactory:
    queries = Queries.load()
    return EngineFactory(queries, tmp_path, limits, SqlGuard(SqlParser(queries), lambda: date(2026, 10, 22)))


def engine(fixture_dir: Path, tmp_path: Path, limits: EngineLimits = LIMITS) -> Engine:
    return factory(tmp_path, limits).open(FixtureSessionProvider(fixture_dir).open())


def resolved(directory: str, **changes: object) -> Resolved:
    values: dict[str, object] = {
        "version": "v1.5.4",
        "autoinstall": False,
        "autoload": False,
        "community": False,
        "unsigned": False,
        "persistent_secrets": False,
        "repository": directory,
        "auto_repository": directory,
        "extension_directory": directory,
        "external_access": True,
        "locked": False,
    }
    values.update(changes)
    return Resolved(**values)  # type: ignore[arg-type]  # test helper: field values vary by case


def test_engine_lists_the_mapping_views(fixture_dir: Path, tmp_path: Path) -> None:
    views = engine(fixture_dir, tmp_path).views()
    assert "mart.yandex_metrika_logs_api__traffic_daily" in views and "dds.yandex_metrika_logs_api__hits" in views


def test_results_are_capped_and_truncation_is_reported(fixture_dir: Path, tmp_path: Path) -> None:
    result = engine(fixture_dir, tmp_path).query(sql("range-10"), 3)
    assert len(result.rows) == 3 and result.truncated
    assert result.columns == (("range", "BIGINT"),)


def test_timestamps_with_time_zone_come_back_as_iso_text(fixture_dir: Path, tmp_path: Path) -> None:
    result = engine(fixture_dir, tmp_path).query(sql("timestamptz"), 10)
    assert result.columns == (("at", "VARCHAR"), ("n", "INTEGER"))
    assert isinstance(result.rows[0][0], str) and result.rows[0][0].startswith("2026-10-22")


def test_text_that_escapes_the_limit_wrapper_is_refused_before_running(fixture_dir: Path, tmp_path: Path) -> None:
    with pytest.raises(QueryRejected):
        engine(fixture_dir, tmp_path).query(sql("wrapper-escape"), 10)


def test_locked_engine_cannot_read_files_outside_the_tenant_folder(fixture_dir: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.csv"
    outside.write_text("a\n1\n")
    with pytest.raises(QueryFailed):
        engine(fixture_dir, tmp_path).query(render(sql("read-file"), {"path": Literal(str(outside))}), 10)


def test_locked_engine_refuses_to_change_settings(fixture_dir: Path, tmp_path: Path) -> None:
    with pytest.raises(QueryFailed):
        engine(fixture_dir, tmp_path).query(sql("set-config"), 10)


def test_long_queries_are_interrupted(fixture_dir: Path, tmp_path: Path) -> None:
    slow = engine(fixture_dir, tmp_path, EngineLimits(memory_limit="512MB", threads=1, timeout_seconds=0.2))
    with pytest.raises(QueryTimeout):
        slow.query(sql("slow"), 1)


def test_missing_mapping_means_no_data_yet(tmp_path: Path) -> None:
    session = DataSession(str(tmp_path / "absent.duckdb"), (str(tmp_path) + "/",), (), None)
    with pytest.raises(NoDataYet):
        factory(tmp_path).open(session)


URL = "https://samovar-t-404.s3.cloud.ru/mapping/samovar.duckdb"


def test_a_refused_key_is_access_denied_and_a_missing_mapping_is_no_data_yet() -> None:
    # The messages DuckDB 1.5 gives when reading an S3 object fails.
    refused = f"HTTP Error: HTTP GET error reading '{URL}' in region 'ru-central-1' (HTTP 403 Forbidden)"
    assert isinstance(storage_failure(refused), AccessDenied)
    assert isinstance(storage_failure(f"HTTP Error: HTTP GET error reading '{URL}' (HTTP 404 Not Found)"), NoDataYet)


def test_digits_in_the_bucket_name_are_not_taken_for_a_status() -> None:
    failure = storage_failure(f"IO Error: Could not establish connection to '{URL}'")
    assert isinstance(failure, UpstreamError) and "connection" in str(failure)


def test_bootstrap_check_refuses_autoinstall_persistent_secrets_and_foreign_repositories(tmp_path: Path) -> None:
    folder = str(tmp_path)
    assert_bootstrap(resolved(folder), tmp_path)
    with pytest.raises(LockdownError, match="autoinstall"):
        assert_bootstrap(resolved(folder, autoinstall=True), tmp_path)
    with pytest.raises(LockdownError, match="persistent secrets"):
        assert_bootstrap(resolved(folder, persistent_secrets=True), tmp_path)
    with pytest.raises(LockdownError, match="repository"):
        assert_bootstrap(resolved(folder, repository="http://x"), tmp_path)


def test_opened_engine_reports_resolved_lockdown(fixture_dir: Path, tmp_path: Path) -> None:
    settings = engine(fixture_dir, tmp_path).settings()
    assert not settings.external_access and settings.locked and not settings.autoinstall
    assert not settings.persistent_secrets
