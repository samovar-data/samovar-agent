import asyncio
import csv
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from samovar_agent.composition import Application
from samovar_agent.settings import DataMode, S3Key
from tests.conftest import build_app, fixture_settings, make_settings
from tests.sql_files import cases, sql

TRAFFIC = "mart.yandex_metrika_logs_api__traffic_daily"
LAST_WEEK = sql("last-week")


def call(app: Application, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = asyncio.run(app.server.call_tool(name, arguments))
    assert isinstance(result, CallToolResult) and not result.is_error, result
    content = result.structured_content
    assert isinstance(content, dict)
    return content


def test_describe_data_lists_tables_available_to_the_key(app: Application) -> None:
    described = call(app, "describe_data", {})
    assert described["data_access"] == "ok" and described["today"] == "2026-10-22"
    available = {table["view"] for table in described["tables"] if table["available"]}
    assert {TRAFFIC, "dds.amocrm__leads", "mart.amocrm__leads_daily"} <= available
    assert "dds.amocrm__tasks" not in available  # in the catalog, not in this tenant's data
    assert [layer["schema"] for layer in described["layers"]] == ["dds", "mart"]
    detail = call(app, "describe_data", {"table": "traffic_daily"})["detail"]
    assert detail["view"] == TRAFFIC and any(field["name"] == "bounces" for field in detail["fields"])


def test_describe_data_notes_each_sources_own_timezone(app: Application) -> None:
    described = call(app, "describe_data", {})
    assert [source["code"] for source in described["sources"]] == ["yandex_metrika_logs_api", "amocrm"]
    assert len(described["notes"]) == 2 and all("own timezone" in note for note in described["notes"])
    assert all("Europe/Moscow" in note for note in described["notes"])


def test_question_flow_runs_sql_then_charts_and_exports_with_the_sql_alongside(app: Application) -> None:
    answer = call(app, "run_query", {"sql": LAST_WEEK, "purpose": "Визиты за прошлую неделю"})
    assert answer["row_count"] == 7 and sum(row[1] for row in answer["rows"]) == 1246
    assert answer["catalog_version"] and answer["sql"] == LAST_WEEK
    spec = {"kind": "line", "title": "Визиты", "x": "dt", "y": ["visits"]}
    chart = call(app, "make_chart", {"query_id": answer["query_id"], "spec": spec})
    page = Path(chart["path"])
    assert page.name == f"vizity-{answer['query_id'][:8]}.html"
    text = page.read_text(encoding="utf-8")
    assert "Визиты" in text and "SamovarChart.mount(" in text
    exported = call(app, "export", {"query_id": answer["query_id"], "format": "csv"})
    assert Path(exported["path"]).name == f"vizity-za-proshluyu-nedelyu-{answer['query_id'][:8]}.csv"
    assert Path(exported["path"]).name.isascii()
    rows = list(csv.reader(Path(exported["path"]).open(encoding="utf-8-sig")))
    assert rows[0] == ["dt", "visits"] and len(rows) == 8
    sql_text = Path(exported["sql_path"]).read_text(encoding="utf-8")
    assert "Визиты за прошлую неделю" in sql_text and LAST_WEEK in sql_text


@pytest.mark.parametrize(("message", "statement"), cases("tool-errors"))
def test_refused_or_failing_queries_come_back_as_tool_errors(app: Application, message: str, statement: str) -> None:
    with pytest.raises(ToolError, match=message):
        asyncio.run(app.server.call_tool("run_query", {"sql": statement, "purpose": "x"}))


def test_unknown_query_id_asks_to_run_the_query_again(app: Application) -> None:
    with pytest.raises(ToolError, match="run the query again"):
        asyncio.run(app.server.call_tool("export", {"query_id": "missing", "format": "json"}))


def test_status_before_describe_reports_the_default_zone_without_loading_the_catalog(app: Application) -> None:
    status = call(app, "status", {})
    assert status["problems"] == [] and status["catalog_version"] is None
    assert status["timezone"] == "Europe/Moscow" and status["today"] == "2026-10-22"


def test_status_does_not_need_a_reachable_catalog(fixture_dir: Path, tmp_path: Path) -> None:
    settings = replace(fixture_settings(fixture_dir, tmp_path), catalog_url="file://" + str(tmp_path / "absent.json"))
    status = call(build_app(settings), "status", {})
    assert status["problems"] == [] and status["catalog_version"] is None


def test_describe_data_reports_date_problems(app: Application) -> None:
    assert call(app, "describe_data", {})["problems"] == []


def test_an_incomplete_s3_key_is_named_by_status_instead_of_stopping_the_server(tmp_path: Path) -> None:
    key = S3Key(key_id="KEYID0123", secret="secret-value-0123", bucket="")
    status = call(build_app(make_settings(tmp_path, DataMode.PLATFORM, s3_key=key)), "status", {})
    assert any("needs all of" in problem for problem in status["problems"]) and status["key_configured"]


def test_status_in_fixture_mode_has_no_problems(app: Application) -> None:
    call(app, "describe_data", {})
    status = call(app, "status", {})
    assert status["problems"] == [] and status["session"]["mode"] == "fixture"
    assert status["today"] == "2026-10-22" and status["timezone"] == "Europe/Moscow"
    assert status["setup_command"].endswith("samovar-agent setup")


def test_chart_without_the_installed_library_asks_to_run_setup(fixture_dir: Path, tmp_path: Path) -> None:
    app = build_app(fixture_settings(fixture_dir, tmp_path), install_charts=False)
    answer = call(app, "run_query", {"sql": LAST_WEEK, "purpose": "x"})
    assert "not installed" in str(call(app, "status", {})["problems"])
    spec = {"kind": "line", "title": "t", "x": "dt", "y": ["visits"]}
    with pytest.raises(ToolError, match="samovar-chart 0.1.1 is not installed: run `.*samovar-agent setup`"):
        asyncio.run(app.server.call_tool("make_chart", {"query_id": answer["query_id"], "spec": spec}))


def test_describe_data_reports_a_timezone_it_cannot_use(fixture_dir: Path, tmp_path: Path) -> None:
    settings = replace(fixture_settings(fixture_dir, tmp_path), timezone_override="Mars/Olympus")
    described = call(build_app(settings), "describe_data", {})
    assert described["timezone"] == "UTC"
    assert described["problems"] == ["Timezone Mars/Olympus is unavailable on this system: dates use UTC."]
