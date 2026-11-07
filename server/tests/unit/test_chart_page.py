import base64
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from samovar_agent.adapters.dist_source import DirectoryDistSource
from samovar_agent.charts.dist import ChartLibrary
from samovar_agent.charts.page import ChartError, ChartPage, column_kind, payload_of
from samovar_agent.charts.theme import bundled_theme
from samovar_agent.domain.chart import ChartKind, ChartSpec, ColumnKind
from samovar_agent.domain.errors import ConfigurationError
from samovar_agent.domain.result import StoredResult
from tests.conftest import REPO
from tests.fakes.chart_dist import FIXTURE, write_dist

RESULT = StoredResult(
    query_id="0123456789abcdef",
    sql="-- golden </script><script>alert(1)</script>",
    purpose="p",
    columns=(("dt", "DATE"), ("visits", "BIGINT"), ("source", "VARCHAR")),
    rows=(("2026-10-01", 10, "</script><b>x</b>"), ("2026-10-02", 12, "ad")),
    truncated=False,
    catalog_version="6.test",
    created_at=datetime(2026, 10, 22, tzinfo=UTC),
)
SPEC = ChartSpec(kind=ChartKind.LINE, title="Визиты <по дням>", x="dt", y=["visits"])


def library(tmp_path: Path, **changes: object) -> ChartLibrary:
    pin = write_dist(tmp_path / "dist", **changes)  # type: ignore[arg-type]  # test helper keywords
    installed = ChartLibrary(
        pin, DirectoryDistSource(tmp_path / "dist"), tmp_path / "cache", "setup", lambda line: None
    )
    installed.install()
    return installed


def page(tmp_path: Path, spec: ChartSpec = SPEC, **changes: object) -> str:
    builder = ChartPage(library(tmp_path, **changes).bundle, bundled_theme)
    return builder.write(spec, RESULT, "footer", tmp_path / "chart.html").read_text(encoding="utf-8")


def scripts(text: str) -> list[str]:
    return re.findall(r"<script>(.*?)</script>", text, flags=re.DOTALL)


def test_page_inlines_the_pinned_bundle_under_a_strict_csp(tmp_path: Path) -> None:
    text = page(tmp_path)
    assert not re.search(r"(src|href)=\"(https?:)?//", text)
    csp = re.search(r'Content-Security-Policy" content="([^"]+)"', text)
    assert csp and "default-src 'none'" in csp.group(1) and "unsafe-eval" not in csp.group(1)
    found = scripts(text)
    assert found[0] == (FIXTURE / "samovar-chart-0.1.1.min.js").read_text(encoding="utf-8")
    assert found[1].startswith("SamovarChart.mount(")
    for script in found:
        digest = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode()
        assert f"'sha256-{digest}'" in csp.group(1)


def test_user_text_cannot_close_a_script_or_inject_markup(tmp_path: Path) -> None:
    text = page(tmp_path)
    assert text.count("</script>") == 3  # payload, bundle, bootstrap
    assert "&lt;/script&gt;&lt;b&gt;x&lt;/b&gt;" in text and "Визиты &lt;по дням&gt;" in text
    payload = re.search(r'id="samovar-payload">(.*?)</script>', text, flags=re.DOTALL)
    assert payload and json.loads(payload.group(1))["spec"]["title"] == SPEC.title


def test_payload_is_checked_against_the_schema_of_the_pinned_library(tmp_path: Path) -> None:
    schema = json.loads((FIXTURE / "chart-payload.schema.json").read_text(encoding="utf-8"))
    schema["$defs"]["ChartSpec"]["properties"]["title"]["maxLength"] = 3
    with pytest.raises(ChartError, match="does not fit samovar-chart 0.1.1 .*spec/title"):
        page(tmp_path, schema=schema)


def test_a_bundle_that_cannot_be_inlined_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="cannot be inlined"):
        page(tmp_path, script=b"var a = '<!-- x';\n")


def test_types_are_classified_for_the_chart_axes() -> None:
    assert column_kind("BIGINT") is column_kind("DECIMAL(18,3)") is ColumnKind.NUMBER
    assert column_kind("DATE") is column_kind("TIMESTAMP WITH TIME ZONE") is ColumnKind.TIME
    assert column_kind("VARCHAR") is column_kind("BIGINT[]") is ColumnKind.TEXT


def test_spec_must_fit_the_result() -> None:
    theme = bundled_theme()
    with pytest.raises(ChartError, match="not in the result"):
        payload_of(SPEC.model_copy(update={"x": "day"}), RESULT, theme, "")
    with pytest.raises(ChartError, match="not numeric"):
        payload_of(SPEC.model_copy(update={"y": ["source"]}), RESULT, theme, "")
    with pytest.raises(ChartError, match="Labels for unknown columns nope"):
        payload_of(SPEC.model_copy(update={"labels": {"nope": "x"}}), RESULT, theme, "")
    with pytest.raises(ChartError, match="exactly one y"):
        payload_of(SPEC.model_copy(update={"y": ["visits", "visits"], "series": "source"}), RESULT, theme, "")


def test_agent_labels_win_over_column_names() -> None:
    spec = SPEC.model_copy(update={"labels": {"dt": "День", "source": "Источник"}})
    labels = [column.label for column in payload_of(spec, RESULT, bundled_theme(), "").data.columns]
    assert labels == ["День", "visits", "Источник"]
    assert [column.label for column in payload_of(SPEC, RESULT, bundled_theme(), "").data.columns] == [
        "dt",
        "visits",
        "source",
    ]


def test_repository_keeps_line_endings_lf() -> None:
    assert "* text=auto eol=lf" in (REPO / ".gitattributes").read_text(encoding="utf-8")
