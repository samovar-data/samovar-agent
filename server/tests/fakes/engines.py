"""An engine factory that fails after the session secret was created and echoes the statement, the way a driver
error message might: proves that redaction, not luck, keeps credentials out of tool output."""

from datetime import date
from pathlib import Path

from samovar_agent.domain.errors import UpstreamError
from samovar_agent.domain.session import DataSession
from samovar_agent.engine.duckdb_engine import Engine, EngineFactory, EngineLimits
from samovar_agent.engine.parser import SqlParser
from samovar_agent.engine.queries import Queries
from samovar_agent.guard.sql_guard import SqlGuard


class EchoingEngineFactory(EngineFactory):
    def __init__(self, extension_dir: Path) -> None:
        queries = Queries.load()
        guard = SqlGuard(SqlParser(queries), lambda: date(2026, 10, 22))
        super().__init__(queries, extension_dir, EngineLimits("256MB", 1, 5), guard)

    def open(self, session: DataSession) -> Engine:
        s3 = session.s3
        assert s3 is not None
        raise UpstreamError(
            f"Could not open the client data: ATTACH failed after CREATE TEMPORARY SECRET (KEY_ID '{s3.key_id}', "
            f"SECRET '{s3.secret}') for "
            f"https://minio.example/b/mapping.duckdb?X-Amz-Credential=x&X-Amz-Signature=y"
        )
