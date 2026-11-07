"""Deterministic eval run: every reference SQL of `evals/questions.yaml` goes through the real guard and the locked
engine over the fixture tenant; answers are compared with the expected rows, refusals are checked against the
catalog (no table, column or tag covers the topic; an item with `source` checks that source's tables only),
rejections must be refused by the guard.

`questions.yaml` is written in the JSON subset of YAML (read with the standard library; no YAML dependency).

    uv run python -m samovar_dev.evals ../evals ../evals/.fixture           # run
    uv run python -m samovar_dev.evals ../evals ../evals/.fixture --record  # fill `expected` for answer items
"""

import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from samovar_agent.adapters.fixture_session import FixtureSessionProvider
from samovar_agent.domain.catalog import Catalog, LayerId
from samovar_agent.domain.errors import QueryRejected
from samovar_agent.domain.values import json_value
from samovar_agent.engine.duckdb_engine import Engine, EngineFactory, EngineLimits
from samovar_agent.engine.parser import SqlParser
from samovar_agent.engine.queries import Queries
from samovar_agent.guard.sql_guard import GuardPolicy, SqlGuard
from samovar_dev.tenant_fixture import CATALOG

QUESTIONS = "questions.yaml"
MAX_ROWS = 500


@dataclass(frozen=True)
class Outcome:
    id: str
    passed: bool
    detail: str


def normalise(rows: Any) -> Any:
    if isinstance(rows, float):
        return round(rows, 6)
    if isinstance(rows, list):
        return [normalise(item) for item in rows]
    return rows


def catalog_names(catalog: Catalog, source: str | None) -> list[str]:
    names: list[str] = []
    for table in catalog.tables:
        if source in (None, table.source_code):
            names += [table.id, table.view, *table.tags, *(column.name for column in table.fields)]
    return [name.lower() for name in names]


class EvalRunner:
    def __init__(self, folder: Path, fixture: Path, catalog: Catalog, scratch: Path) -> None:
        self._folder = folder
        self._document = json.loads((folder / QUESTIONS).read_text(encoding="utf-8"))
        self._catalog = catalog
        queries = Queries.load()
        today = date.fromisoformat(self._document["today"])
        self._guard = SqlGuard(SqlParser(queries), lambda: today)
        self._policy = GuardPolicy(
            window_days=int(self._document["window_days"]),
            date_columns={t.view: t.date_column for t in catalog.tables if t.layer is LayerId.DDS and t.date_column},
            views=catalog.views(),
        )
        factory = EngineFactory(
            queries,
            scratch,
            EngineLimits(memory_limit="1GB", threads=2, timeout_seconds=30),
            self._guard,
        )
        self._engine: Engine = factory.open(FixtureSessionProvider(fixture).open())

    @property
    def questions(self) -> list[dict[str, Any]]:
        return list(self._document["questions"])

    def answer(self, item: dict[str, Any]) -> dict[str, Any]:
        sql = (self._folder / item["sql"]).read_text(encoding="utf-8")
        accepted = self._guard.check(sql, self._policy)
        missing = set(item["tables"]) - set(accepted.tables)
        if missing:
            raise AssertionError(f"reference SQL does not read {sorted(missing)}")
        raw = self._engine.query(accepted.sql, MAX_ROWS)
        return {
            "columns": [name for name, _ in raw.columns],
            "rows": normalise([[json_value(value) for value in row] for row in raw.rows]),
        }

    def run(self, item: dict[str, Any]) -> Outcome:
        kind = item["kind"]
        if kind == "answer":
            try:
                actual = self.answer(item)
            except (QueryRejected, AssertionError) as error:
                return Outcome(item["id"], False, f"reference SQL failed: {error}")
            same = actual == item["expected"]
            return Outcome(
                item["id"],
                same,
                "ok" if same else f"expected {item['expected']}, got {actual}",
            )
        if kind == "reject":
            try:
                self._guard.check(
                    (self._folder / item["sql"]).read_text(encoding="utf-8"),
                    self._policy,
                )
            except QueryRejected as error:
                return Outcome(item["id"], True, f"rejected: {error}")
            return Outcome(item["id"], False, "the guard accepted a statement it must refuse")
        names = catalog_names(self._catalog, item.get("source"))
        hits = [
            term for term in item["absent_terms"] for name in names if re.search(rf"(^|[_\s.]){re.escape(term)}", name)
        ]
        return Outcome(
            item["id"],
            not hits,
            "no covering data" if not hits else f"catalog covers {sorted(set(hits))}",
        )

    def record(self) -> None:
        for item in self._document["questions"]:
            if item["kind"] == "answer":
                item["expected"] = self.answer(item)
        text = json.dumps(self._document, ensure_ascii=False, indent=2) + "\n"
        (self._folder / QUESTIONS).write_text(text, encoding="utf-8")

    def close(self) -> None:
        self._engine.close()


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: evals <evals dir> <fixture dir> [--record]", file=sys.stderr)
        return 2
    catalog = Catalog.model_validate_json(CATALOG.read_bytes())
    fixture = Path(argv[1]).resolve()
    runner = EvalRunner(Path(argv[0]).resolve(), fixture, catalog, fixture / "ext")
    try:
        if "--record" in argv:
            runner.record()
        outcomes = [runner.run(item) for item in runner.questions]
    finally:
        runner.close()
    for outcome in outcomes:
        print(f"{'PASS' if outcome.passed else 'FAIL'} {outcome.id}: {outcome.detail[:160]}")
    failed = [outcome for outcome in outcomes if not outcome.passed]
    print(f"{len(outcomes) - len(failed)}/{len(outcomes)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
