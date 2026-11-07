from pathlib import Path

from samovar_agent.domain.catalog import Catalog
from samovar_dev.evals import EvalRunner
from tests.conftest import REPO


def test_every_eval_question_passes_through_the_guard_and_engine(
    fixture_dir: Path, catalog: Catalog, tmp_path: Path
) -> None:
    runner = EvalRunner(REPO / "evals", fixture_dir, catalog, tmp_path)
    try:
        outcomes = [runner.run(item) for item in runner.questions]
    finally:
        runner.close()
    assert 40 <= len(outcomes) <= 50
    failed = [f"{outcome.id}: {outcome.detail}" for outcome in outcomes if not outcome.passed]
    assert failed == []


def test_eval_set_has_answers_over_both_sources_refusals_and_guard_rejections(
    fixture_dir: Path, catalog: Catalog, tmp_path: Path
) -> None:
    runner = EvalRunner(REPO / "evals", fixture_dir, catalog, tmp_path)
    kinds = [item["kind"] for item in runner.questions]
    tables = {table for item in runner.questions for table in item.get("tables", [])}
    runner.close()
    assert kinds.count("refuse") >= 4 and kinds.count("reject") >= 3 and kinds.count("answer") >= 25
    assert {"mart.amocrm__leads_daily", "dds.amocrm__leads"} <= tables
