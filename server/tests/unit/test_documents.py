import json
from pathlib import Path

import pytest

from samovar_agent.adapters.document_source import FileDocumentSource, HttpDocumentSource, document_source
from samovar_agent.charts.theme import bundled_theme
from samovar_agent.domain.catalog import Catalog, LayerId
from samovar_agent.domain.errors import UpstreamError
from samovar_agent.domain.theme import Theme
from samovar_agent.ports.http import HttpResponse
from samovar_dev.tenant_fixture import CATALOG
from tests.fakes.http import FakeHttpClient

URL = "https://samovardata.example/api/v1/catalog"


def test_the_platform_catalog_describes_metrika_and_amocrm_tables_with_columns(catalog: Catalog) -> None:
    assert [source.code for source in catalog.sources] == ["yandex_metrika_logs_api", "amocrm"]
    assert {table.source_code for table in catalog.tables} == {"yandex_metrika_logs_api", "amocrm"}
    assert {"dds.yandex_metrika_logs_api__visits", "dds.amocrm__leads", "mart.amocrm__leads_daily"} <= catalog.views()
    for table in catalog.tables:
        assert table.fields and all(column.description for column in table.fields)
        assert table.date_column == "dt"
    assert {table.layer for table in catalog.tables} == {LayerId.DDS, LayerId.MART}
    assert [layer.schema_name for layer in catalog.layers] == ["dds", "mart"]


def test_fields_the_agent_does_not_read_are_ignored_and_the_version_follows_the_content(catalog: Catalog) -> None:
    raw = json.loads(CATALOG.read_text(encoding="utf-8"))
    raw["future_field"] = {"added": "by a later platform version"}
    assert Catalog.model_validate(raw) == catalog
    raw["tables"][0]["title"] = "changed"
    assert Catalog.model_validate(raw).catalog_version != catalog.catalog_version


def test_the_catalog_is_loaded_from_the_configured_url() -> None:
    http = FakeHttpClient({("GET", URL): HttpResponse(200, CATALOG.read_bytes())})
    catalog = HttpDocumentSource(http, URL, Catalog).load()
    assert catalog.catalog_version and http.requests[0].url == URL


def test_unavailable_or_foreign_documents_are_reported() -> None:
    with pytest.raises(UpstreamError, match="HTTP 404"):
        HttpDocumentSource(FakeHttpClient(), URL, Catalog).load()
    wrong = json.dumps({"tables": 2}).encode()
    with pytest.raises(UpstreamError, match="supported schema"):
        HttpDocumentSource(FakeHttpClient({("GET", URL): HttpResponse(200, wrong)}), URL, Catalog).load()


def test_file_urls_read_local_documents_and_report_missing_files(tmp_path: Path) -> None:
    assert document_source("file://" + str(CATALOG), FakeHttpClient(), Catalog).load().tables
    with pytest.raises(UpstreamError, match="unreadable"):
        FileDocumentSource(tmp_path / "missing.json", Catalog).load()


def test_theme_fonts_cannot_break_out_of_css() -> None:
    data = bundled_theme().model_dump()
    data["font"] = "x; } </style><script>"
    with pytest.raises(ValueError):
        Theme.model_validate(data)


def test_theme_series_must_be_hex_colours() -> None:
    data = bundled_theme().model_dump()
    data["light"]["series"] = ["#0f5c63", "red; background:url(x)"]
    with pytest.raises(ValueError):
        Theme.model_validate(data)
