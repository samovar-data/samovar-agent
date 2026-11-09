from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from samovar_agent.adapters.demo_session import DemoSnapshot
from samovar_agent.composition import Application, build
from samovar_agent.domain.catalog import Catalog
from samovar_agent.engine.duckdb_engine import EngineFactory
from samovar_agent.ports.http import HttpClient
from samovar_agent.settings import DataMode, S3Key, Settings
from samovar_dev.tenant_fixture import CATALOG, build_fixture
from tests.fakes.chart_dist import write_dist
from tests.fakes.clock import FixedClock

REPO = Path(__file__).resolve().parents[2]
TODAY = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)


@pytest.fixture(scope="session")
def catalog() -> Catalog:
    return Catalog.model_validate_json(CATALOG.read_bytes())


@pytest.fixture(scope="session")
def fixture_dir(tmp_path_factory: pytest.TempPathFactory, catalog: Catalog) -> Path:
    folder = tmp_path_factory.mktemp("tenant")
    build_fixture(folder, catalog)
    return folder


def make_settings(work: Path, mode: DataMode, fixture_dir: Path | None = None, s3_key: S3Key | None = None) -> Settings:
    return Settings(
        catalog_url="file://" + str(CATALOG),
        timezone_override=None,
        plugin_root=REPO,
        data_mode=mode,
        data_dir=work / "data",
        output_dir=work / "out",
        fixture_dir=fixture_dir,
        chart_dist_dir=work / "chart-dist",
        s3_key=s3_key,
    )


def build_app(
    settings: Settings,
    http: HttpClient | None = None,
    engines: EngineFactory | None = None,
    install_charts: bool = True,
    demo_pin: DemoSnapshot | None = None,
) -> Application:
    """The real composition with the test clock and the stub chart library (installed unless told otherwise)."""
    assert settings.chart_dist_dir is not None
    pin = write_dist(settings.chart_dist_dir)
    app = build(settings, lambda message: None, FixedClock(TODAY), http, engines, pin, demo_pin)
    if install_charts:
        app.chart_library.install()
    return app


def fixture_settings(fixture_dir: Path, work: Path) -> Settings:
    return make_settings(work, DataMode.FIXTURE, fixture_dir)


@pytest.fixture
def app(fixture_dir: Path, tmp_path: Path) -> Iterator[Application]:
    yield build_app(fixture_settings(fixture_dir, tmp_path))
