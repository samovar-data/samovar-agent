"""The query engine: one locked DuckDB connection over the tenant's read-only mapping database."""

import re
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from samovar_agent.domain.errors import (
    AccessDenied,
    ExtensionError,
    LockdownError,
    NoDataYet,
    QueryFailed,
    QueryTimeout,
    SamovarError,
    UpstreamError,
)
from samovar_agent.domain.session import DataSession
from samovar_agent.engine.queries import Queries
from samovar_agent.engine.settings import (
    Resolved,
    assert_bootstrap,
    assert_locked,
    connection_config,
)
from samovar_agent.engine.sql_template import (
    Boolean,
    Identifier,
    Integer,
    Literal,
    LiteralList,
    Statement,
    TextCasts,
    render,
)
from samovar_agent.guard.sql_guard import SqlGuard

NOT_PUBLISHED = re.compile(r"\b404\b|not found|no such file|does not exist", re.IGNORECASE)
NO_DATA = "No published data yet: the tenant's mapping is not available."
URL = re.compile(r"\S+://\S*")
REFUSED = re.compile(r"\b(401|403)\b|forbidden|access denied|signature", re.IGNORECASE)


@dataclass(frozen=True)
class EngineLimits:
    memory_limit: str
    threads: int
    timeout_seconds: float


@dataclass(frozen=True)
class RawResult:
    columns: tuple[tuple[str, str], ...]
    rows: tuple[tuple[Any, ...], ...]
    truncated: bool
    elapsed_ms: int


class Engine:
    def __init__(
        self, conn: duckdb.DuckDBPyConnection, queries: Queries, limits: EngineLimits, guard: SqlGuard
    ) -> None:
        self._conn = conn
        self._queries = queries
        self._limits = limits
        self._guard = guard

    def query(self, accepted_sql: str, max_rows: int) -> RawResult:
        """Run a statement already accepted by the guard, capped at `max_rows` (one extra row detects truncation)."""
        sql = render(
            self._queries.wrap_query,
            {"query": Statement(accepted_sql), "limit": Integer(max_rows + 1)},
        )
        self._guard.single_select(sql)  # defence in depth: the wrapped text is still exactly one SELECT
        timer = threading.Timer(self._limits.timeout_seconds, self._conn.interrupt)
        started = time.perf_counter()
        timer.start()
        try:
            sql = self._text_timestamps(sql)
            cursor = self._conn.execute(sql)
            columns = tuple((str(item[0]), str(item[1])) for item in cursor.description or ())
            rows = cursor.fetchmany(max_rows + 1)
        except duckdb.InterruptException as error:
            raise QueryTimeout(
                f"The query ran longer than {self._limits.timeout_seconds:g} s and was stopped. "
                "Narrow the period or aggregate in a mart."
            ) from error
        except duckdb.Error as error:
            raise QueryFailed(_first_line(error)) from error
        finally:
            timer.cancel()
        return RawResult(
            columns=columns,
            rows=tuple(tuple(row) for row in rows[:max_rows]),
            truncated=len(rows) > max_rows,
            elapsed_ms=round((time.perf_counter() - started) * 1000),
        )

    def _text_timestamps(self, sql: str) -> str:
        """TIMESTAMP WITH TIME ZONE values would need pytz in Python: DuckDB renders them as ISO text instead."""
        relation = self._conn.sql(sql)
        zoned = tuple(name for name, kind in zip(relation.columns, relation.types) if "WITH TIME ZONE" in str(kind))
        if not zoned:
            return sql
        return render(self._queries.text_timestamps, {"query": Statement(sql), "casts": TextCasts(zoned)})

    def views(self) -> tuple[str, ...]:
        rows = self._conn.execute(self._queries.views).fetchall()
        return tuple(f"{schema}.{name}" for schema, name in rows)

    def settings(self) -> Resolved:
        return resolved(self._conn, self._queries)

    def close(self) -> None:
        self._conn.close()


class EngineFactory:
    """Opens a locked engine for one data session (lock_configuration forbids changing it afterwards)."""

    def __init__(self, queries: Queries, extension_dir: Path, limits: EngineLimits, guard: SqlGuard) -> None:
        self._queries = queries
        self._extension_dir = extension_dir
        self._limits = limits
        self._guard = guard

    def open(self, session: DataSession) -> Engine:
        config = connection_config(self._extension_dir, self._limits.memory_limit, self._limits.threads)
        conn = duckdb.connect(":memory:", config=config)
        try:
            self._setup(conn, session)
        except duckdb.Error as error:
            conn.close()
            raise UpstreamError(f"Could not open the client data: {_first_line(error)}") from error
        except BaseException:
            conn.close()
            raise
        return Engine(conn, self._queries, self._limits, self._guard)

    def _setup(self, conn: duckdb.DuckDBPyConnection, session: DataSession) -> None:
        assert_bootstrap(resolved(conn, self._queries), self._extension_dir)
        for name in session.extensions:
            try:
                conn.execute(render(self._queries.load_extension, {"name": Identifier(name)}))
            except duckdb.Error as error:
                raise ExtensionError(
                    f"DuckDB extension {name} is not installed or invalid: run `samovar-agent setup`."
                ) from error
        if session.s3 is not None:
            s3 = session.s3
            conn.execute(
                render(
                    self._queries.s3_defaults,
                    {
                        "endpoint": Literal(s3.endpoint),
                        "url_style": Literal(s3.url_style),
                        "use_ssl": Boolean(s3.use_ssl),
                        "region": Literal(s3.region),
                    },
                )
            )
            conn.execute(
                render(
                    self._queries.secret,
                    {
                        "key_id": Literal(s3.key_id),
                        "secret": Literal(s3.secret),
                        "endpoint": Literal(s3.endpoint),
                        "region": Literal(s3.region),
                        "url_style": Literal(s3.url_style),
                        "use_ssl": Boolean(s3.use_ssl),
                        "scope": Literal(s3.scope),
                    },
                )
            )
        try:
            conn.execute(
                render(
                    self._queries.attach,
                    {"location": Literal(session.mapping_location)},
                )
            )
        except duckdb.Error as error:
            failure = self._why_unattached(conn, session.mapping_location)
            if failure is None:
                raise
            raise failure from error
        conn.execute(self._queries.use)
        attached = conn.execute(self._queries.attached).fetchone()
        if attached is None or not attached[1]:
            raise LockdownError("mapping is not attached read-only")
        if session.demo_shift_days is not None:
            conn.execute(render(self._queries.set_demo_shift, {"days": Integer(session.demo_shift_days)}))
        conn.execute(
            render(
                self._queries.lock,
                {"allowed_directories": LiteralList(session.allowed_directories)},
            )
        )
        assert_locked(resolved(conn, self._queries))
        if session.s3 is not None:
            endpoint = conn.execute(self._queries.s3_endpoint).fetchone()
            if endpoint is None or endpoint[0] != session.s3.endpoint:
                raise LockdownError("global S3 endpoint is not the session endpoint")

    def _why_unattached(self, conn: duckdb.DuckDBPyConnection, location: str) -> SamovarError | None:
        """ATTACH reports a refused key and a missing mapping alike ("database does not exist"); reading the object's
        size tells them apart (an S3 error names the HTTP status, a missing local file reads as no rows). None: the
        object is there, so the ATTACH error itself stands."""
        try:
            found = conn.execute(render(self._queries.object_size, {"location": Literal(location)})).fetchall()
        except duckdb.Error as error:
            return storage_failure(str(error))
        return None if found else NoDataYet(NO_DATA)


def storage_failure(message: str) -> SamovarError:
    """What a failed read of the mapping object means for the user; URLs are cut out first, so that digits or words
    in a bucket name are not taken for a status."""
    status = URL.sub("", message)
    if REFUSED.search(status):
        return AccessDenied(
            "The storage refused the S3 key: check the Access Key ID, the secret and the bucket; a revoked or "
            "expired key (keys live a year) needs a new one from the cabinet."
        )
    if NOT_PUBLISHED.search(status):
        return NoDataYet(NO_DATA)
    return UpstreamError(f"Could not open the client data: {_first_line(message)}")


def resolved(conn: duckdb.DuckDBPyConnection, queries: Queries) -> Resolved:
    cursor = conn.execute(queries.resolved)
    row = cursor.fetchone()
    if row is None:
        raise LockdownError("settings are unreadable")
    values = dict(zip((str(item[0]) for item in cursor.description or ()), row))
    return Resolved(
        version=str(values["version"]),
        autoinstall=_flag(values["autoinstall"]),
        autoload=_flag(values["autoload"]),
        community=_flag(values["community"]),
        unsigned=_flag(values["unsigned"]),
        persistent_secrets=_flag(values["persistent_secrets"]),
        repository=str(values["repository"]),
        auto_repository=str(values["auto_repository"]),
        extension_directory=str(values["extension_directory"]),
        external_access=_flag(values["external_access"]),
        locked=_flag(values["locked"]),
    )


def _flag(value: object) -> bool:
    return value is True or str(value).lower() == "true"


def _first_line(error: object) -> str:
    lines: Sequence[str] = str(error).strip().splitlines() or [type(error).__name__]
    return lines[0]
