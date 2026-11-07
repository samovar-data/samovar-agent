"""Entry point: `samovar-agent [serve|setup|status]`. The only place that reads the process environment."""

import argparse
import json
import os
import sys
from pathlib import Path

from samovar_agent.composition import build, configure_logging
from samovar_agent.domain.errors import SamovarError
from samovar_agent.settings import DataMode, Settings

# Plugin root of a source checkout (server/src/samovar_agent/cli.py -> repository root); the plugin passes
# SAMOVAR_PLUGIN_ROOT explicitly.
SOURCE_ROOT = Path(__file__).resolve().parents[3]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="samovar-agent", description="Samovar Data analyst MCP server")
    parser.add_argument("command", nargs="?", default="serve", choices=["serve", "setup", "status"])
    args = parser.parse_args(argv)

    def log(message: str) -> None:
        print(message, file=sys.stderr)

    try:
        settings = Settings.from_env(os.environ, Path.cwd(), Path.home(), SOURCE_ROOT)
        app = build(settings, log)
    except SamovarError as error:
        log(f"samovar-agent: {error}")
        return 2
    configure_logging(app.redactor)
    if args.command == "setup":
        try:
            installed = app.installer.install() if settings.data_mode is DataMode.PLATFORM else []
            library = app.chart_library.install()
        except SamovarError as error:
            log(f"samovar-agent setup failed: {app.redactor.redact(str(error))}")
            return 1
        log(f"samovar-agent setup: {len(installed)} extension(s) verified and installed in {settings.extension_dir}")
        log(f"samovar-agent setup: chart library verified and installed in {library}")
        return 0
    if args.command == "status":
        print(
            json.dumps(
                app.service.status().model_dump(mode="json"),
                ensure_ascii=False,
                indent=1,
            )
        )
        return 0
    app.server.run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
