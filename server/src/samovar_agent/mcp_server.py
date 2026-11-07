"""MCP registration of the analyst tools (stdio). The one boundary where errors are translated and output redacted."""

import functools
import logging
from collections.abc import Callable
from typing import Annotated, ParamSpec, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from samovar_agent.domain.chart import ChartSpec
from samovar_agent.domain.errors import SamovarError
from samovar_agent.domain.tools import (
    DescribeDataOutput,
    ExportFormat,
    ExportOutput,
    MakeChartOutput,
    RunQueryOutput,
    StatusOutput,
)
from samovar_agent.redact import Redactor
from samovar_agent.service.analyst import AnalystService

SERVER_NAME = "samovar"
INSTRUCTIONS = (
    "Samovar Data analyst tools over the client's own data. Always call describe_data first, write DuckDB SQL only "
    "against the views it lists (detail-layer day bounds as DATE literals), show the SQL and the catalog version "
    "with every answer, and say plainly when the data cannot answer the question."
)
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITES_FILES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)

P = ParamSpec("P")
M = TypeVar("M", bound=BaseModel)
log = logging.getLogger("samovar_agent")


def redact_values(redactor: Redactor, value: object) -> object:
    """Redacts every string inside a JSON-like value (redacting serialized JSON text could break its syntax)."""
    if isinstance(value, str):
        return redactor.redact(value)
    if isinstance(value, list):
        return [redact_values(redactor, item) for item in value]
    if isinstance(value, dict):
        return {key: redact_values(redactor, item) for key, item in value.items()}
    return value


def boundary(redactor: Redactor) -> Callable[[Callable[P, M]], Callable[P, M]]:
    """Domain errors become tool errors with a redacted message; any other error is logged (redacted) and reported
    generically; every successful output is redacted as well (defence in depth for secrets in data or messages).
    """

    def decorate(function: Callable[P, M]) -> Callable[P, M]:
        @functools.wraps(function)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> M:
            try:
                output = function(*args, **kwargs)
            except SamovarError as error:
                raise ToolError(redactor.redact(str(error))) from None
            except Exception:
                log.exception("tool %s failed", function.__name__)
                raise ToolError("Internal error in the samovar agent; details are in the MCP server log.") from None
            return type(output).model_validate(redact_values(redactor, output.model_dump(mode="json")))

        return wrapper

    return decorate


def build_server(service: AnalystService, redactor: Redactor, version: str) -> MCPServer:
    server: MCPServer = MCPServer(SERVER_NAME, instructions=INSTRUCTIONS, version=version, log_level="WARNING")
    guard = boundary(redactor)

    @guard
    def describe_data(
        table: Annotated[str | None, Field(description="Table id or view name for full details.")] = None,
    ) -> DescribeDataOutput:
        """Describe the client's data: sources, layers, tables (with availability for this key), excluded fields,
        and for one table its grain, key, day rule (with its timezone), notes and columns. Call it before writing SQL.
        """
        return service.describe_data(table)

    @guard
    def run_query(
        sql: Annotated[str, Field(description="One DuckDB SELECT over dds.* / mart.* views.")],
        purpose: Annotated[str, Field(description="What the query answers, in the user's words.")],
    ) -> RunQueryOutput:
        """Run one read-only SELECT. Detail-layer (dds) queries must filter the day column; results are capped (see
        `truncated`). Returns a query_id for make_chart and export."""
        return service.run_query(sql, purpose)

    @guard
    def make_chart(query_id: str, spec: ChartSpec) -> MakeChartOutput:
        """Draw an interactive chart (Apache ECharts, site theme, light/dark) from a stored result as one
        self-contained HTML page with the data and the SQL; the page has a "save as PNG" button."""
        return service.make_chart(query_id, spec)

    @guard
    def export(query_id: str, format: ExportFormat) -> ExportOutput:
        """Export the full result of a stored query (re-run up to the export limit) as CSV, JSON or XLSX, with the SQL
        saved next to it."""
        return service.export(query_id, format)

    @guard
    def status() -> StatusOutput:
        """Versions, S3 key and extension readiness, data access state; lists problems with the fix for each."""
        return service.status()

    server.add_tool(describe_data, annotations=READ_ONLY, structured_output=True)
    server.add_tool(run_query, annotations=READ_ONLY, structured_output=True)
    server.add_tool(make_chart, annotations=WRITES_FILES, structured_output=True)
    server.add_tool(export, annotations=WRITES_FILES, structured_output=True)
    server.add_tool(status, annotations=READ_ONLY, structured_output=True)
    return server
