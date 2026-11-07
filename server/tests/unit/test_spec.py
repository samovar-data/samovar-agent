from pathlib import Path

from samovar_dev.schemas import offline_server, render, schemas
from tests.conftest import REPO


def test_committed_json_schemas_match_their_sources(tmp_path: Path) -> None:
    for name, schema in schemas(offline_server(tmp_path)).items():
        committed = (REPO / "spec" / name).read_text(encoding="utf-8")
        assert committed == render(schema), f"spec/{name} is stale: run python -m samovar_dev.schemas ../spec"


def test_tool_contract_lists_exactly_the_five_tools(tmp_path: Path) -> None:
    tools = schemas(offline_server(tmp_path))["tools.schema.json"]["tools"]
    assert [tool["name"] for tool in tools] == [
        "describe_data",
        "run_query",
        "make_chart",
        "export",
        "status",
    ]
    assert all("outputSchema" in tool for tool in tools)
