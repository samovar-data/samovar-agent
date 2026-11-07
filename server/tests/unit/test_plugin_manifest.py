import json
import re
import tomllib

from samovar_agent.settings import PREFIX
from tests.conftest import REPO

PLUGIN = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
MCP = json.loads((REPO / ".mcp.json").read_text(encoding="utf-8"))
SERVER = MCP["mcpServers"]["samovar"]


def test_every_user_config_reference_is_declared_and_the_key_is_sensitive() -> None:
    referenced = set(re.findall(r"\$\{user_config\.(\w+)\}", json.dumps(MCP)))
    assert referenced == set(PLUGIN["userConfig"])
    assert PLUGIN["userConfig"]["s3_key_id"]["sensitive"] is True
    assert PLUGIN["userConfig"]["s3_secret"]["sensitive"] is True


def test_server_environment_passes_the_plugin_settings_and_data_folder() -> None:
    names = {name.removeprefix(PREFIX) for name in SERVER["env"] if name.startswith(PREFIX)}
    assert names == {
        "DATA_DIR",
        "PLUGIN_ROOT",
        "S3_KEY_ID",
        "S3_SECRET",
        "S3_BUCKET",
        "S3_ENDPOINT",
        "S3_REGION",
        "API_URL",
        "OUTPUT_DIR",
    }


def test_server_runs_from_the_frozen_lock_without_dev_tools() -> None:
    assert SERVER["command"] == "uv" and {"--frozen", "--no-dev"} <= set(SERVER["args"])
    assert SERVER["env"]["UV_PROJECT_ENVIRONMENT"].startswith("${CLAUDE_PLUGIN_DATA}")


def test_plugin_and_server_versions_match() -> None:
    project = tomllib.loads((REPO / "server" / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert PLUGIN["version"] == project["version"]
