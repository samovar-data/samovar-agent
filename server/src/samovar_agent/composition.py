"""Composition root: settings are read once here and every dependency is wired here (and only here)."""

import logging
import shlex
import sys
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from types import MappingProxyType

from mcp.server.mcpserver import MCPServer

from samovar_agent.adapters.demo_session import DemoSessionProvider, DemoSnapshot
from samovar_agent.adapters.dist_source import DirectoryDistSource, HttpDistSource
from samovar_agent.adapters.document_source import document_source
from samovar_agent.adapters.fixture_session import FixtureSessionProvider
from samovar_agent.adapters.s3_key_session import S3KeySessionProvider
from samovar_agent.adapters.system_clock import SystemClock
from samovar_agent.adapters.urllib_http import UrllibHttpClient
from samovar_agent.charts.dist import ChartLibrary, DistPin
from samovar_agent.charts.page import ChartPage
from samovar_agent.charts.theme import bundled_theme
from samovar_agent.domain.catalog import Catalog
from samovar_agent.engine.duckdb_engine import EngineFactory, EngineLimits
from samovar_agent.engine.parser import SqlParser
from samovar_agent.engine.platform import duckdb_platform
from samovar_agent.engine.queries import Queries
from samovar_agent.engine.settings import DUCKDB_VERSION
from samovar_agent.export.writers import WRITERS
from samovar_agent.extensions.installer import ExtensionInstaller
from samovar_agent.extensions.manifest import ExtensionManifest
from samovar_agent.guard.sql_guard import SqlGuard
from samovar_agent.mcp_server import build_server
from samovar_agent.phone_home import assert_no_telemetry, disable_mcp_telemetry
from samovar_agent.ports.clock import Clock
from samovar_agent.ports.http import HttpClient
from samovar_agent.ports.session import DataSessionProvider
from samovar_agent.redact import RedactingFilter, Redactor
from samovar_agent.service.analyst import AnalystService, ServiceConfig
from samovar_agent.service.catalog_cache import CatalogCache
from samovar_agent.service.data_access import DataAccess
from samovar_agent.service.data_day import DataDay
from samovar_agent.service.results import ResultStore
from samovar_agent.settings import DEFAULT_TIMEZONE, DataMode, Settings

API_TIMEOUT_SECONDS = 30.0
API_MAX_BYTES = 8 * 1024 * 1024
EXTENSION_TIMEOUT_SECONDS = 300.0
EXTENSION_MAX_BYTES = 64 * 1024 * 1024
DEMO_TIMEOUT_SECONDS = 120.0
DEMO_MAX_BYTES = 32 * 1024 * 1024  # the snapshot is about 3 MB
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Application:
    settings: Settings
    service: AnalystService
    server: MCPServer
    installer: ExtensionInstaller
    chart_library: ChartLibrary
    redactor: Redactor


@dataclass(frozen=True)
class SessionInputs:
    settings: Settings
    data_day: DataDay
    http: HttpClient | None
    demo_pin: DemoSnapshot | None


SESSION_PROVIDERS: Mapping[DataMode, Callable[[SessionInputs], DataSessionProvider]] = MappingProxyType(
    {
        DataMode.PLATFORM: lambda inputs: S3KeySessionProvider(inputs.settings.s3_key),
        DataMode.FIXTURE: lambda inputs: FixtureSessionProvider(inputs.settings.fixture_dir or Path(".")),
        DataMode.DEMO: lambda inputs: DemoSessionProvider(
            inputs.demo_pin or DemoSnapshot.load(),
            inputs.http or UrllibHttpClient(DEMO_TIMEOUT_SECONDS, DEMO_MAX_BYTES),
            inputs.settings.demo_dir,
            inputs.data_day,
        ),
    }
)


def setup_command(settings: Settings) -> str:
    data = shlex.quote(str(settings.data_dir))
    venv = shlex.quote(str(settings.data_dir / "venv"))
    project = shlex.quote(str(settings.plugin_root / "server"))
    return (
        f"UV_PROJECT_ENVIRONMENT={venv} SAMOVAR_DATA_DIR={data} "
        f"uv run --frozen --quiet --no-dev --project {project} samovar-agent setup"
    )


def build(
    settings: Settings,
    log_line: Callable[[str], None],
    clock: Clock | None = None,
    http: HttpClient | None = None,
    engines: EngineFactory | None = None,
    chart_pin: DistPin | None = None,
    demo_pin: DemoSnapshot | None = None,
) -> Application:
    """Wires the application; `clock`, the catalog `http` client, `engines`, the chart library pin and the demo
    snapshot pin are replaced only by tests."""
    queries = Queries.load()
    wall: Clock = clock or SystemClock()
    api_http = http or UrllibHttpClient(API_TIMEOUT_SECONDS, API_MAX_BYTES)
    catalog = CatalogCache(document_source(settings.catalog_url, api_http, Catalog))
    data_day = DataDay(wall, settings.timezone_override, DEFAULT_TIMEZONE)
    today = data_day.today
    platform = duckdb_platform(queries)
    installer = ExtensionInstaller(
        UrllibHttpClient(EXTENSION_TIMEOUT_SECONDS, EXTENSION_MAX_BYTES),
        ExtensionManifest.load(),
        settings.extension_dir,
        platform,
        log_line,
    )
    limits = settings.limits
    guard = SqlGuard(SqlParser(queries), today)
    data = DataAccess(
        SESSION_PROVIDERS[settings.data_mode](SessionInputs(settings, data_day, http, demo_pin)),
        engines
        or EngineFactory(
            queries,
            settings.extension_dir,
            EngineLimits(limits.memory_limit, limits.threads, limits.timeout_seconds),
            guard,
        ),
        today,
    )
    pin = chart_pin or DistPin.load()
    dist_source = (
        DirectoryDistSource(settings.chart_dist_dir)
        if settings.chart_dist_dir
        else HttpDistSource(UrllibHttpClient(EXTENSION_TIMEOUT_SECONDS, EXTENSION_MAX_BYTES), pin.base_url)
    )
    chart_library = ChartLibrary(pin, dist_source, settings.chart_cache_dir, setup_command(settings), log_line)
    agent_version = version("samovar-agent")
    service = AnalystService(
        config=ServiceConfig(
            agent_version=agent_version,
            duckdb_version=DUCKDB_VERSION,
            platform=platform,
            catalog_url=settings.catalog_url,
            output_dir=settings.output_dir,
            limits=limits,
            key_configured=settings.s3_key is not None,
            needs_extensions=settings.data_mode is DataMode.PLATFORM,
            setup_command=setup_command(settings),
        ),
        catalog=catalog,
        data_day=data_day,
        data=data,
        guard=guard,
        results=ResultStore(limits.stored_results),
        charts=ChartPage(chart_library.bundle, bundled_theme),
        chart_library=chart_library,
        writers=WRITERS,
        extensions=installer,
        clock=wall,
        new_id=lambda: uuid.uuid4().hex,
    )
    key = settings.s3_key
    secrets = (key.key_id, key.secret) if key else ()
    redactor = Redactor(lambda: (*secrets, *data.secrets()))
    server = build_server(service, redactor, agent_version)
    disable_mcp_telemetry(server)
    assert_no_telemetry(server)
    return Application(
        settings=settings,
        service=service,
        server=server,
        installer=installer,
        chart_library=chart_library,
        redactor=redactor,
    )


def configure_logging(redactor: Redactor) -> None:
    """Logs go to stderr (stdout is the MCP stdio channel), through the redacting filter."""
    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(RedactingFilter(redactor))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.WARNING)
