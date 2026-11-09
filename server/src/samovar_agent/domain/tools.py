"""Outputs of the MCP tools. `spec/tools.schema.json` is generated from the registered tools (inputs from the tool
signatures in `samovar_agent.mcp_server`, outputs from these models)."""

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from samovar_agent.domain.catalog import Excluded, Layer, Source, Table


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ExportFormat(StrEnum):
    CSV = "csv"
    JSON = "json"
    XLSX = "xlsx"


DATA_MODE = '"platform", "fixture" or "demo": demo is synthetic sample data, not the user\'s own.'


class TableSummary(Model):
    id: str
    layer: str
    view: str
    title: str
    purpose: str
    available: bool = Field(description="True when the view is present in the tenant's mapping.")


class DescribeDataOutput(Model):
    catalog_version: str
    today: date = Field(description="Today in the data's timezone: use it to turn relative periods into DATE literals.")
    timezone: str = Field(description="The zone of `today`; each source's day is in that source's own zone.")
    sources: list[Source] = Field(description="The connected sources the catalog describes.")
    notes: list[str] = Field(
        description="Facts to respect: one per source (its timezone), and in demo mode a DEMO DATA note."
    )
    problems: list[str] = Field(description="Problems with the dates (a timezone fallback).")
    data_mode: str = Field(description=DATA_MODE)
    data_access: str = Field(description='"ok", or why the client data could not be opened (descriptions still apply).')
    layers: list[Layer]
    tables: list[TableSummary]
    excluded: list[Excluded]
    detail: Table | None = None


class ResultColumn(Model):
    name: str
    type: str


class RunQueryOutput(Model):
    query_id: str
    sql: str
    purpose: str
    columns: list[ResultColumn]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    elapsed_ms: int
    catalog_version: str
    data_mode: str = Field(description=DATA_MODE)


class MakeChartOutput(Model):
    query_id: str
    path: str = Field(description="Self-contained HTML page with the interactive chart, the data and the SQL.")
    data_mode: str = Field(description=DATA_MODE)


class ExportOutput(Model):
    query_id: str
    path: str
    sql_path: str
    row_count: int
    truncated: bool
    data_mode: str = Field(description=DATA_MODE)


class ExtensionStatus(Model):
    name: str
    installed: bool


class ChartLibraryStatus(Model):
    name: str
    version: str
    installed: bool


class SessionStatus(Model):
    mode: str
    open: bool


class StatusOutput(Model):
    agent_version: str
    duckdb_version: str
    platform: str
    key_configured: bool = Field(description="True when an S3 key is entered; `problems` says if it is incomplete.")
    catalog_url: str
    catalog_version: str | None
    today: date
    timezone: str
    extensions: list[ExtensionStatus]
    chart_library: ChartLibraryStatus
    session: SessionStatus
    output_dir: str
    setup_command: str = Field(description="Exact command that installs the DuckDB extensions for this server.")
    problems: list[str]
