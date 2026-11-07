"""A chart as one self-contained HTML file: the pinned samovar-chart bundle (ECharts inside) inlined, the payload as
JSON, a strict CSP with script hashes (no CDN, no eval, no inline handlers). Python validates the spec against the
result, assembles the payload and checks it against the library's own schema; the chart is drawn by the library
when the page opens."""

import base64
import hashlib
import html
import json
import re
from collections.abc import Callable
from importlib import resources
from pathlib import Path
from string import Template

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]  # jsonschema ships no type information
from jsonschema.exceptions import best_match  # type: ignore[import-untyped]  # jsonschema ships no type information

from samovar_agent.charts.dist import ChartBundle
from samovar_agent.domain.chart import ChartColumn, ChartData, ChartPayload, ChartSpec, ColumnKind
from samovar_agent.domain.errors import SamovarError
from samovar_agent.domain.result import StoredResult
from samovar_agent.domain.theme import Palette, Theme
from samovar_agent.domain.values import JsonValue

NUMERIC = re.compile(r"^(U?(TINYINT|SMALLINT|INTEGER|BIGINT|HUGEINT)|FLOAT|DOUBLE|REAL|DECIMAL(\(\d+,\s*\d+\))?)$")
TIME = re.compile(r"^(DATE|TIME|TIMESTAMP)\b")
TABLE_ROWS = 200
GLOBAL_NAME = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
BOOTSTRAP = (
    "{name}.mount(document.getElementById('samovar-chart'), "
    "JSON.parse(document.getElementById('samovar-payload').textContent));"
)


class ChartError(SamovarError):
    """The spec does not fit the result (unknown or non-numeric columns)."""


def column_kind(duckdb_type: str) -> ColumnKind:
    if NUMERIC.match(duckdb_type):
        return ColumnKind.NUMBER
    if TIME.match(duckdb_type):
        return ColumnKind.TIME
    return ColumnKind.TEXT


def payload_of(spec: ChartSpec, result: StoredResult, theme: Theme, footer: str) -> ChartPayload:
    columns = [
        ChartColumn(name=name, type=kind, kind=column_kind(kind), label=spec.labels.get(name, name))
        for name, kind in result.columns
    ]
    by_name = {column.name: column for column in columns}
    for name in [spec.x, *spec.y, *([spec.series] if spec.series else [])]:
        if name not in by_name:
            raise ChartError(f"Column {name!r} is not in the result; available: {', '.join(by_name)}.")
    for name in spec.y:
        if by_name[name].kind is not ColumnKind.NUMBER:
            raise ChartError(f"Column {name!r} is not numeric and cannot be plotted on the value axis.")
    unknown = sorted(set(spec.labels) - set(by_name))
    if unknown:
        raise ChartError(f"Labels for unknown columns {', '.join(unknown)}; available: {', '.join(by_name)}.")
    if spec.series is not None and len(spec.y) != 1:
        raise ChartError("With `series` set, give exactly one y column.")
    return ChartPayload(
        spec=spec, data=ChartData(columns=columns, rows=[list(row) for row in result.rows]), theme=theme, footer=footer
    )


def check_payload(payload: ChartPayload, bundle: ChartBundle) -> None:
    """The payload must satisfy the input schema of the pinned library version (the contract is the library's)."""
    error = best_match(Draft202012Validator(bundle.payload_schema).iter_errors(payload.model_dump(mode="json")))
    if error is not None:
        where = "/".join(str(part) for part in error.absolute_path) or "payload"
        raise ChartError(
            f"The chart does not fit samovar-chart {bundle.version} (schema {bundle.schema_version}): "
            f"{where}: {error.message}"
        )


def script_json(value: str) -> str:
    """JSON safe inside <script>: no '<' (so no '</script>'), no line separators."""
    return value.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def csp_hash(script: str) -> str:
    return "'sha256-" + base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii") + "'"


def css_colors(theme: Theme) -> str:
    def block(palette: Palette) -> str:
        names = {"bg": palette.background, "surface": palette.surface, "text": palette.text}
        names.update({"muted": palette.muted, "border": palette.border})
        return " ".join(f"--{name}: {value};" for name, value in names.items())

    return (
        f":root {{ {block(theme.light)} }}\n@media (prefers-color-scheme: dark) {{ :root {{ {block(theme.dark)} }} }}"
    )


class ChartPage:
    def __init__(self, bundle: Callable[[], ChartBundle], theme: Callable[[], Theme]) -> None:
        self._bundle = bundle
        self._theme = theme
        self._template = Template(resources.files("samovar_agent.charts").joinpath("chart.html").read_text("utf-8"))

    def write(self, spec: ChartSpec, result: StoredResult, footer: str, path: Path) -> Path:
        theme = self._theme()
        payload = payload_of(spec, result, theme, footer)
        bundle = self._bundle()
        check_payload(payload, bundle)
        if not GLOBAL_NAME.match(bundle.global_name):
            raise ChartError(f"Unexpected global name {bundle.global_name!r} in the chart library manifest")
        bootstrap = BOOTSTRAP.format(name=bundle.global_name)
        csp = (
            f"default-src 'none'; script-src {csp_hash(bundle.script)} {csp_hash(bootstrap)}; "
            "style-src 'unsafe-inline'; img-src data: blob:"
        )
        page = self._template.substitute(
            csp=csp,
            title=html.escape(spec.title),
            colors=css_colors(theme),
            font=theme.font,
            mono=theme.mono_font,
            radius=theme.radius_px,
            head="".join(f"<th>{html.escape(column.label)}</th>" for column in payload.data.columns),
            body="".join(
                "<tr>" + "".join(f"<td>{html.escape(_cell(value))}</td>" for value in row) + "</tr>"
                for row in result.rows[:TABLE_ROWS]
            ),
            more=f"<p>Показано {TABLE_ROWS} из {len(result.rows)} строк.</p>" if len(result.rows) > TABLE_ROWS else "",
            sql=html.escape(result.sql),
            footer=html.escape(footer),
            payload=script_json(payload.model_dump_json()),
            bundle=bundle.script,
            bootstrap=bootstrap,
        )
        path.write_text(page, encoding="utf-8")
        return path


def _cell(value: JsonValue) -> str:
    if value is None:
        return "∅"
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value)
