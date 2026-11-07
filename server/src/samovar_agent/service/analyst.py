"""The analyst tools: describe the data, run a guarded query, chart it, export it, report status."""

import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from samovar_agent.charts.dist import ChartLibrary
from samovar_agent.charts.page import ChartPage
from samovar_agent.domain.catalog import Catalog, LayerId
from samovar_agent.domain.chart import ChartSpec
from samovar_agent.domain.errors import SamovarError
from samovar_agent.domain.result import StoredResult
from samovar_agent.domain.tools import (
    DescribeDataOutput,
    ExportFormat,
    ExportOutput,
    MakeChartOutput,
    ResultColumn,
    RunQueryOutput,
    SessionStatus,
    StatusOutput,
    TableSummary,
)
from samovar_agent.domain.values import json_value
from samovar_agent.export.writers import Writer
from samovar_agent.extensions.installer import ExtensionInstaller
from samovar_agent.guard.sql_guard import GuardPolicy, SqlGuard
from samovar_agent.ports.clock import Clock
from samovar_agent.service.catalog_cache import CatalogCache
from samovar_agent.service.data_access import DataAccess
from samovar_agent.service.data_day import DataDay
from samovar_agent.service.filenames import output_name
from samovar_agent.service.results import ResultStore
from samovar_agent.settings import Limits


@dataclass(frozen=True)
class ServiceConfig:
    agent_version: str
    duckdb_version: str
    platform: str
    catalog_url: str
    output_dir: Path
    limits: Limits
    key_configured: bool
    needs_extensions: bool
    setup_command: str


class AnalystService:
    def __init__(
        self,
        config: ServiceConfig,
        catalog: CatalogCache,
        data_day: DataDay,
        data: DataAccess,
        guard: SqlGuard,
        results: ResultStore,
        charts: ChartPage,
        writers: Mapping[ExportFormat, Writer],
        extensions: ExtensionInstaller,
        chart_library: ChartLibrary,
        clock: Clock,
        new_id: Callable[[], str],
    ) -> None:
        self._config = config
        self._catalog = catalog
        self._data_day = data_day
        self._data = data
        self._guard = guard
        self._results = results
        self._charts = charts
        self._writers = writers
        self._extensions = extensions
        self._chart_library = chart_library
        self._clock = clock
        self._new_id = new_id
        # MCP runs sync tools in worker threads; one DuckDB connection and the caches are used one call at a time.
        self._lock = threading.RLock()

    def catalog(self) -> Catalog:
        return self._catalog()

    def secrets(self) -> tuple[str, ...]:
        return self._data.secrets()

    def describe_data(self, table: str | None = None) -> DescribeDataOutput:
        with self._lock:
            catalog = self.catalog()
            detail = None
            if table is not None:
                detail = catalog.table(table)
                if detail is None:
                    raise SamovarError(f"No table {table!r} in the catalog; call describe_data without arguments.")
            try:
                views = set(self._data.engine().views())
                access = "ok"
            except SamovarError as error:
                views, access = set(), str(error)
            zone = self._data_day.zone()
            return DescribeDataOutput(
                catalog_version=catalog.catalog_version,
                today=self._data_day.today(),
                timezone=zone.name,
                sources=catalog.sources,
                problems=list(zone.problems),
                notes=[
                    f"{source.title} ({source.code}): dt is the day in this source's own timezone, see each "
                    f"table's day_rule; `today` is the day in {zone.name}."
                    for source in catalog.sources
                ],
                data_access=access,
                layers=catalog.layers,
                tables=[
                    TableSummary(
                        id=item.id,
                        layer=item.layer.value,
                        view=item.view,
                        title=item.title,
                        purpose=item.purpose,
                        available=item.view in views,
                    )
                    for item in catalog.tables
                ],
                excluded=catalog.excluded,
                detail=detail,
            )

    def run_query(self, sql: str, purpose: str) -> RunQueryOutput:
        with self._lock:
            catalog = self.catalog()
            engine = self._data.engine()
            accepted = self._guard.check(sql, self._policy(catalog, engine.views()))
            raw = engine.query(accepted.sql, self._config.limits.max_rows)
            result = StoredResult(
                query_id=self._new_id(),
                sql=accepted.sql,
                purpose=purpose,
                columns=raw.columns,
                rows=tuple(tuple(json_value(value) for value in row) for row in raw.rows),
                truncated=raw.truncated,
                catalog_version=catalog.catalog_version,
                created_at=self._clock.now(),
            )
            self._results.put(result)
            return RunQueryOutput(
                query_id=result.query_id,
                sql=result.sql,
                purpose=purpose,
                columns=[ResultColumn(name=name, type=kind) for name, kind in result.columns],
                rows=[list(row) for row in result.rows],
                row_count=len(result.rows),
                truncated=result.truncated,
                elapsed_ms=raw.elapsed_ms,
                catalog_version=result.catalog_version,
            )

    def make_chart(self, query_id: str, spec: ChartSpec) -> MakeChartOutput:
        with self._lock:
            result = self._results.get(query_id)
            path = self._output_path(spec.title, query_id, "chart").with_suffix(".html")
            self._charts.write(spec, result, footer(result), path)
            return MakeChartOutput(query_id=query_id, path=str(path))

    def export(self, query_id: str, export_format: ExportFormat) -> ExportOutput:
        with self._lock:
            stored = self._results.get(query_id)
            raw = self._data.engine().query(stored.sql, self._config.limits.export_max_rows)
            base = self._output_path(stored.purpose, query_id, "export")
            path = base.with_suffix("." + export_format.value)
            rows = [[json_value(value) for value in row] for row in raw.rows]
            self._writers[export_format](path, [name for name, _ in raw.columns], rows)
            sql_path = base.with_suffix(".sql")
            sql_path.write_text(sql_file(stored), encoding="utf-8")
            return ExportOutput(
                query_id=query_id,
                path=str(path),
                sql_path=str(sql_path),
                row_count=len(rows),
                truncated=raw.truncated,
            )

    def status(self) -> StatusOutput:
        with self._lock:
            extensions = self._extensions.status()
            zone = self._data_day.zone()
            problems: list[str] = list(zone.problems)
            access = self._data.problem()
            if access is not None:
                problems.append(access)
            missing = [item.name for item in extensions if not item.installed]
            if self._config.needs_extensions and missing:
                problems.append(
                    f"DuckDB extensions not installed ({', '.join(missing)}): run `{self._config.setup_command}`."
                )
            chart_library = self._chart_library.status()
            if not chart_library.installed:
                problems.append(
                    f"Chart library {chart_library.name} {chart_library.version} is not installed: "
                    f"run `{self._config.setup_command}`."
                )
            return StatusOutput(
                agent_version=self._config.agent_version,
                duckdb_version=self._config.duckdb_version,
                platform=self._config.platform,
                key_configured=self._config.key_configured,
                catalog_url=self._config.catalog_url,
                catalog_version=self._catalog.loaded.catalog_version if self._catalog.loaded else None,
                today=self._data_day.today(),
                timezone=zone.name,
                extensions=extensions,
                chart_library=chart_library,
                session=SessionStatus(mode=self._data.mode, open=self._data.session is not None),
                output_dir=str(self._config.output_dir),
                setup_command=self._config.setup_command,
                problems=problems,
            )

    def _policy(self, catalog: Catalog, views: tuple[str, ...]) -> GuardPolicy:
        return GuardPolicy(
            window_days=self._config.limits.dds_window_days,
            date_columns={
                table.view: table.date_column
                for table in catalog.tables
                if table.layer is LayerId.DDS and table.date_column
            },
            views=catalog.views() | frozenset(views),
        )

    def _output_path(self, title: str, query_id: str, fallback: str) -> Path:
        self._config.output_dir.mkdir(parents=True, exist_ok=True)
        return self._config.output_dir / output_name(title, query_id, fallback)


def footer(result: StoredResult) -> str:
    created = f"{result.created_at:%Y-%m-%d %H:%M %Z}"
    return f"Samovar Data · catalog {result.catalog_version} · query {result.query_id[:8]} · {created}"


def sql_file(result: StoredResult) -> str:
    header = [
        "-- " + " ".join(result.purpose.split()),
        f"-- catalog {result.catalog_version}; query {result.query_id}; {result.created_at.isoformat()}",
    ]
    return "\n".join(header) + "\n" + result.sql.rstrip() + ";\n"
