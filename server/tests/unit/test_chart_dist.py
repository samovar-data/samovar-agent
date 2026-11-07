import json
from pathlib import Path

import pytest

from samovar_agent.adapters.dist_source import DirectoryDistSource, HttpDistSource
from samovar_agent.charts.dist import ChartLibrary, ChartLibraryMissing, DistPin
from samovar_agent.domain.errors import ConfigurationError, UpstreamError
from samovar_agent.ports.http import HttpResponse
from tests.fakes.chart_dist import SCRIPT, write_dist
from tests.fakes.http import FakeHttpClient


def library(source_dir: Path, cache: Path, pin: DistPin) -> ChartLibrary:
    return ChartLibrary(pin, DirectoryDistSource(source_dir), cache, "samovar-agent setup", lambda line: None)


def test_pinned_version_installs_and_loads(tmp_path: Path) -> None:
    pin = write_dist(tmp_path / "dist")
    installed = library(tmp_path / "dist", tmp_path / "cache", pin)
    assert not installed.status().installed
    folder = installed.install()
    assert folder == tmp_path / "cache" / "samovar-chart" / "0.1.1" and installed.status().installed
    bundle = installed.bundle()
    assert bundle.global_name == "SamovarChart" and bundle.schema_version == 1 and "SamovarChart" in bundle.script


def test_a_manifest_that_differs_from_the_pin_installs_nothing(tmp_path: Path) -> None:
    pin = write_dist(tmp_path / "dist").model_copy(update={"manifest_sha256": "0" * 64})
    with pytest.raises(UpstreamError, match="pinned sha256"):
        library(tmp_path / "dist", tmp_path / "cache", pin).install()
    assert not (tmp_path / "cache").exists()


def test_a_file_that_differs_from_the_manifest_installs_nothing(tmp_path: Path) -> None:
    pin = write_dist(tmp_path / "dist")
    (tmp_path / "dist" / SCRIPT).write_text("tampered", encoding="utf-8")
    with pytest.raises(UpstreamError, match="does not match its sha256"):
        library(tmp_path / "dist", tmp_path / "cache", pin).install()
    assert not (tmp_path / "cache").exists()


def test_manifest_file_names_cannot_leave_the_version_folder(tmp_path: Path) -> None:
    pin = write_dist(tmp_path / "dist")
    manifest_path = tmp_path / "dist" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["../evil.js"] = manifest["files"][SCRIPT]
    raw = json.dumps(manifest).encode()
    manifest_path.write_bytes(raw)
    import hashlib

    pin = pin.model_copy(update={"manifest_sha256": hashlib.sha256(raw).hexdigest()})
    with pytest.raises(UpstreamError, match="Unexpected file name"):
        library(tmp_path / "dist", tmp_path / "cache", pin).install()


def test_not_installed_or_tampered_copies_ask_to_run_setup(tmp_path: Path) -> None:
    pin = write_dist(tmp_path / "dist")
    installed = library(tmp_path / "dist", tmp_path / "cache", pin)
    with pytest.raises(ChartLibraryMissing, match="not installed: run `samovar-agent setup`"):
        installed.bundle()
    installed.install()
    (tmp_path / "cache" / "samovar-chart" / "0.1.1" / SCRIPT).write_text("tampered", encoding="utf-8")
    fresh = library(tmp_path / "dist", tmp_path / "cache", pin)
    with pytest.raises(ChartLibraryMissing, match="does not match its sha256"):
        fresh.bundle()


def test_published_files_are_fetched_from_the_pinned_url(tmp_path: Path) -> None:
    pin = write_dist(tmp_path / "dist")
    http = FakeHttpClient(
        {
            ("GET", pin.base_url + name): HttpResponse(200, (tmp_path / "dist" / name).read_bytes())
            for name in ("manifest.json", SCRIPT, "chart-payload.schema.json")
        }
    )
    installed = ChartLibrary(pin, HttpDistSource(http, pin.base_url), tmp_path / "cache", "setup", lambda line: None)
    installed.install()
    assert [request.url for request in http.requests][0] == pin.base_url + "manifest.json"
    assert installed.bundle().version == "0.1.1"


def test_the_shipped_pin_names_a_published_version() -> None:
    pin = DistPin.load()
    assert pin.name == "samovar-chart" and pin.base_url.endswith(f"/samovar-chart/{pin.version}/")
    assert pin.base_url.startswith("https://global.s3.cloud.ru/samovar-data-static/")


def test_status_reports_installed_only_for_the_pinned_manifest(tmp_path: Path) -> None:
    pin = write_dist(tmp_path / "dist")
    installed = library(tmp_path / "dist", tmp_path / "cache", pin)
    installed.install()
    assert installed.status().installed
    (tmp_path / "cache" / "samovar-chart" / "0.1.1" / "manifest.json").write_text("{}", encoding="utf-8")
    assert not installed.status().installed


def test_a_copy_changed_after_the_first_chart_is_caught_at_the_next_one(tmp_path: Path) -> None:
    pin = write_dist(tmp_path / "dist")
    installed = library(tmp_path / "dist", tmp_path / "cache", pin)
    installed.install()
    installed.bundle()
    (tmp_path / "cache" / "samovar-chart" / "0.1.1" / SCRIPT).write_text("changed", encoding="utf-8")
    with pytest.raises(ChartLibraryMissing, match="does not match its sha256"):
        installed.bundle()


def test_a_library_speaking_another_schema_version_is_refused(tmp_path: Path) -> None:
    pin = write_dist(tmp_path / "dist", schema_version=2)
    installed = library(tmp_path / "dist", tmp_path / "cache", pin)
    installed.install()
    with pytest.raises(ConfigurationError, match="speaks chart schema 2, this plugin supports 1"):
        installed.bundle()
