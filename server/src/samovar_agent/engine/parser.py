"""SQL parsing through DuckDB's own parser (`json_serialize_sql`) on an empty, locked in-memory connection."""

import json
from typing import Any, cast

import duckdb

from samovar_agent.engine.queries import Queries
from samovar_agent.engine.settings import locked_parser_config


class SqlParser:
    def __init__(self, queries: Queries) -> None:
        self._queries = queries
        self._conn: duckdb.DuckDBPyConnection | None = None

    def parse(self, sql: str) -> dict[str, Any]:
        """The parse tree as DuckDB serializes it: `{"error": bool, "error_message": ..., "statements": [...]}`."""
        if self._conn is None:
            self._conn = duckdb.connect(":memory:", config=locked_parser_config())
        row = self._conn.execute(self._queries.serialize, {"sql": sql}).fetchone()
        return cast(dict[str, Any], json.loads(row[0])) if row else {"error": True, "statements": []}

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
