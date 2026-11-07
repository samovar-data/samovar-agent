"""The DuckDB platform string (osx_arm64, linux_amd64, ...) used in extension paths."""

import duckdb

from samovar_agent.engine.queries import Queries
from samovar_agent.engine.settings import locked_parser_config


def duckdb_platform(queries: Queries) -> str:
    with duckdb.connect(":memory:", config=locked_parser_config()) as conn:
        row = conn.execute(queries.platform).fetchone()
    return str(row[0]) if row else "unknown"
