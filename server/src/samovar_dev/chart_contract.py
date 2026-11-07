"""Development check of the contract with a local samovar-chart build (the neighbour repository's `dist/`):

1. the pinned manifest sha256 (`samovar_agent/charts/chart-dist.json`) is the sha256 of that build's manifest;
2. the ChartSpec and Theme models of the plugin declare exactly the library's schemas (all constraints);
3. chart pages of every kind are built from it, so every payload passes the library's payload schema.

    uv run python -m samovar_dev.chart_contract ../../samovar-chart/dist
"""

import hashlib
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from samovar_agent.adapters.dist_source import DirectoryDistSource
from samovar_agent.charts.dist import MANIFEST, ChartLibrary, DistPin
from samovar_agent.charts.page import ChartPage
from samovar_agent.charts.theme import bundled_theme
from samovar_agent.domain.chart import ChartKind, ChartSpec
from samovar_agent.domain.result import StoredResult
from samovar_agent.domain.theme import Theme

RESULT = StoredResult(
    query_id="0123456789abcdef",
    sql="-- contract check, no SQL is run",
    purpose="contract",
    columns=(("dt", "DATE"), ("source", "VARCHAR"), ("visits", "BIGINT"), ("share", "DOUBLE")),
    rows=(("2026-10-01", "ad", 10, 0.5), ("2026-10-01", "organic", 20, 0.5), ("2026-10-02", "ad", 12, 0.4)),
    truncated=False,
    catalog_version="contract",
    created_at=datetime(2026, 10, 22, tzinfo=UTC),
)


META = frozenset({"$schema", "$id", "title", "description", "x-schema-version"})


def normalised(schema: dict[str, Any]) -> dict[str, Any]:
    """A schema without its identity fields (id, title, version marker): only the constraints are compared."""
    return {key: value for key, value in schema.items() if key not in META}


def same_schema(model: type[BaseModel], schema: dict[str, Any]) -> list[str]:
    """The plugin's model and the library's schema must declare exactly the same constraints (properties, required,
    enums, lengths, ...), or make_chart would advertise one contract and the payload check enforce another."""
    ours, theirs = normalised(model.model_json_schema()), normalised(schema)
    if ours == theirs:
        return []
    differing = sorted(key for key in set(ours) | set(theirs) if ours.get(key) != theirs.get(key))
    fields = sorted(
        name
        for name in set(ours.get("properties", {})) | set(theirs.get("properties", {}))
        if ours.get("properties", {}).get(name) != theirs.get("properties", {}).get(name)
    )
    return [f"{model.__name__}: schema differs from the library in {differing} (properties: {fields})"]


def check(dist: Path) -> list[str]:
    problems: list[str] = []
    pin = DistPin.load()
    digest = hashlib.sha256((dist / MANIFEST).read_bytes()).hexdigest()
    if digest != pin.manifest_sha256:
        problems.append(f"pin {pin.manifest_sha256} != local build {digest}: update chart-dist.json after publishing")
    problems += same_schema(ChartSpec, json.loads((dist / "chartspec.schema.json").read_text(encoding="utf-8")))
    problems += same_schema(Theme, json.loads((dist / "theme.schema.json").read_text(encoding="utf-8")))
    with tempfile.TemporaryDirectory() as work:
        local_pin = pin.model_copy(update={"manifest_sha256": digest})
        library = ChartLibrary(local_pin, DirectoryDistSource(dist), Path(work), "setup", lambda line: None)
        library.install()
        page = ChartPage(library.bundle, bundled_theme)
        specs = [ChartSpec(kind=kind, title=kind.value, x="dt", y=["visits"]) for kind in ChartKind]
        specs.append(
            ChartSpec(kind=ChartKind.BAR, title="s", x="dt", y=["visits"], series="source", labels={"dt": "День"})
        )
        for index, spec in enumerate(specs):
            page.write(spec, RESULT, "contract", Path(work) / f"chart-{index}.html")
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: chart_contract <samovar-chart dist dir>", file=sys.stderr)
        return 2
    problems = check(Path(argv[0]))
    for problem in problems:
        print(problem, file=sys.stderr)
    print("chart contract: " + ("FAIL" if problems else "ok"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
