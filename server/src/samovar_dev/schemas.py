"""Generates the JSON Schemas in `spec/` from their single sources (pydantic models and the registered MCP tools).

uv run python -m samovar_dev.schemas ../spec          # write
uv run python -m samovar_dev.schemas ../spec --check  # fail if a committed schema is stale
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from samovar_agent.composition import build
from samovar_agent.domain.catalog import Catalog
from samovar_agent.settings import DataMode, Settings

SPEC_ID = "https://samovardata.ru/spec/agent/"


def with_meta(schema: dict[str, Any], name: str, title: str) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SPEC_ID + name,
        "title": title,
        **schema,
    }


def tools_schema(server: MCPServer) -> dict[str, Any]:
    tools = asyncio.run(server.list_tools())
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SPEC_ID + "tools.schema.json",
        "title": "samovar-agent MCP tools",
        "description": "Tool contract of the samovar MCP server: name, description, input and output schema.",
        "tools": [
            tool.model_dump(
                mode="json",
                by_alias=True,
                exclude_none=True,
                include={
                    "name",
                    "description",
                    "input_schema",
                    "output_schema",
                    "annotations",
                },
            )
            for tool in tools
        ],
    }


def schemas(server: MCPServer) -> dict[str, dict[str, Any]]:
    return {
        "catalog.schema.json": with_meta(
            Catalog.model_json_schema(),
            "catalog.schema.json",
            "Samovar data catalog (GET /api/v1/catalog): the fields the agent reads",
        ),
        "tools.schema.json": tools_schema(server),
    }


def offline_server(work: Path) -> MCPServer:
    settings = Settings(
        catalog_url="file://" + str(work / "catalog.json"),
        timezone_override="UTC",
        plugin_root=work,
        data_mode=DataMode.FIXTURE,
        data_dir=work,
        output_dir=work,
        fixture_dir=work,
    )
    return build(settings, lambda message: None).server


def render(schema: dict[str, Any]) -> str:
    return json.dumps(schema, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: schemas <spec dir> [--check]", file=sys.stderr)
        return 2
    spec = Path(argv[0])
    stale = []
    for name, schema in schemas(offline_server(spec)).items():
        path = spec / name
        text = render(schema)
        if "--check" in argv:
            if not path.is_file() or path.read_text(encoding="utf-8") != text:
                stale.append(name)
        else:
            path.write_text(text, encoding="utf-8")
    if stale:
        print(
            f"stale schemas (regenerate with samovar_dev.schemas): {', '.join(stale)}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
