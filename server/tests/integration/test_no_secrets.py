"""No part of the client's S3 key or a presigned URL may reach tool output or logs."""

import asyncio
import logging
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from samovar_agent.composition import Application, configure_logging
from samovar_agent.domain.errors import SamovarError
from samovar_agent.domain.tools import StatusOutput
from samovar_agent.engine.duckdb_engine import EngineFactory
from samovar_agent.mcp_server import boundary
from samovar_agent.redact import RedactingFilter, Redactor
from samovar_agent.settings import DataMode
from tests.conftest import build_app, make_settings
from tests.fakes.engines import EchoingEngineFactory
from tests.fakes.s3_key import KEY_ID, SECRET, s3_key
from tests.sql_files import sql

FORBIDDEN = (KEY_ID, SECRET, "X-Amz-")


def platform_app(tmp_path: Path, engines: EngineFactory | None = None) -> Application:
    return build_app(make_settings(tmp_path, DataMode.PLATFORM, s3_key=s3_key()), engines=engines)


def structured(result: object) -> str:
    assert isinstance(result, CallToolResult)
    return str(result.structured_content)


def assert_clean(text: str) -> None:
    for value in FORBIDDEN:
        assert value not in text


def exercise(app: Application, caplog: pytest.LogCaptureFixture) -> str:
    caplog.set_level(logging.DEBUG)
    described = structured(asyncio.run(app.server.call_tool("describe_data", {})))
    assert_clean(described)
    with pytest.raises(ToolError) as error:
        asyncio.run(app.server.call_tool("run_query", {"sql": sql("mart-all"), "purpose": "x"}))
    assert_clean(str(error.value))
    assert_clean(structured(asyncio.run(app.server.call_tool("status", {}))))
    assert_clean(caplog.text)
    return described


def test_missing_extensions_in_platform_mode_leak_no_secrets(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    described = exercise(platform_app(tmp_path), caplog)
    assert "samovar-agent setup" in described  # extensions are absent: data access says how to fix it


def test_errors_after_the_secret_was_created_are_redacted(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    described = exercise(platform_app(tmp_path, EchoingEngineFactory(tmp_path)), caplog)
    assert "CREATE TEMPORARY SECRET" in described and "[redacted]" in described


def test_boundary_redacts_error_messages() -> None:
    @boundary(Redactor(lambda: (KEY_ID, SECRET)))
    def leaky() -> StatusOutput:
        raise SamovarError(f"failed {SECRET} at https://s3.example/x?X-Amz-Signature=abc with {KEY_ID}")

    with pytest.raises(ToolError) as error:
        leaky()
    assert_clean(str(error.value))


def test_logging_goes_to_stderr_through_the_redacting_filter() -> None:
    root = logging.getLogger()
    saved = root.handlers[:]
    try:
        configure_logging(Redactor(lambda: ()))
        assert any(isinstance(item, RedactingFilter) for handler in root.handlers for item in handler.filters)
    finally:
        root.handlers[:] = saved
