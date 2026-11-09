import asyncio
from pathlib import Path
from typing import Any

from mcp.types import CallToolResult

from samovar_agent.composition import Application
from samovar_agent.ports.http import HttpResponse
from samovar_agent.settings import DataMode
from tests.conftest import build_app, make_settings
from tests.fakes.demo_snapshot import build_snapshot
from tests.fakes.http import FakeHttpClient
from tests.sql_files import sql


def call(app: Application, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = asyncio.run(app.server.call_tool(name, arguments))
    assert isinstance(result, CallToolResult) and not result.is_error, result
    content = result.structured_content
    assert isinstance(content, dict)
    return content


def test_demo_mode_needs_no_key_and_every_answer_says_the_data_is_demo(tmp_path: Path) -> None:
    pin, body = build_snapshot(tmp_path)
    http = FakeHttpClient({("GET", pin.url): HttpResponse(200, body)})
    app = build_app(make_settings(tmp_path, DataMode.DEMO), http=http, demo_pin=pin)
    described = call(app, "describe_data", {})
    assert described["data_mode"] == "demo" and described["data_access"] == "ok"
    assert any("DEMO DATA" in note for note in described["notes"])
    answer = call(app, "run_query", {"sql": sql("demo-last-day"), "purpose": "last day"})
    assert answer["data_mode"] == "demo" and answer["rows"] == [["2026-10-21"]]  # yesterday of the test clock
    status = call(app, "status", {})
    assert status["session"]["mode"] == "demo" and status["problems"] == [] and not status["key_configured"]


def test_charts_and_exports_of_demo_data_are_marked_demo(tmp_path: Path) -> None:
    pin, body = build_snapshot(tmp_path)
    http = FakeHttpClient({("GET", pin.url): HttpResponse(200, body)})
    app = build_app(make_settings(tmp_path, DataMode.DEMO), http=http, demo_pin=pin)
    answer = call(app, "run_query", {"sql": sql("demo-visits-by-day"), "purpose": "visits"})
    chart = call(
        app,
        "make_chart",
        {"query_id": answer["query_id"], "spec": {"kind": "line", "title": "Visits", "x": "dt", "y": ["visits"]}},
    )
    exported = call(app, "export", {"query_id": answer["query_id"], "format": "csv"})
    assert chart["data_mode"] == exported["data_mode"] == "demo"
    assert "DEMO DATA" in Path(chart["path"]).read_text(encoding="utf-8")
    assert "DEMO DATA" in Path(exported["sql_path"]).read_text(encoding="utf-8")
