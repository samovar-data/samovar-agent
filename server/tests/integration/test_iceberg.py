"""The platform's mapping views read Iceberg (`iceberg_scan` over a table's metadata file): the locked engine reads
such a view anywhere in the tenant's folder (as in its bucket: the folder name does not matter) and refuses one
over another folder (as another bucket).

Needs the pinned avro and iceberg extensions, installed by `samovar-agent setup` into `~/.samovar-agent/ext` or the
folder named by SAMOVAR_TEST_EXTENSION_DIR; skipped without them (no network in tests).
"""

import json
import os
from datetime import date
from pathlib import Path

import duckdb
import pytest

from samovar_agent.domain.errors import QueryFailed
from samovar_agent.domain.session import DataSession
from samovar_agent.engine.duckdb_engine import Engine, EngineFactory, EngineLimits
from samovar_agent.engine.parser import SqlParser
from samovar_agent.engine.platform import duckdb_platform
from samovar_agent.engine.queries import Queries
from samovar_agent.engine.settings import DUCKDB_VERSION, DuckDbConfig
from samovar_agent.engine.sql_template import Identifier, Integer, Literal, render
from samovar_agent.guard.sql_guard import SqlGuard
from tests.sql_files import cases, sql

EXTENSIONS = Path(os.environ.get("SAMOVAR_TEST_EXTENSION_DIR") or Path.home() / ".samovar-agent" / "ext")
QUERIES = Queries.load()
TABLE = dict(cases("iceberg-table"))
pytestmark = pytest.mark.skipif(
    not (EXTENSIONS / DUCKDB_VERSION / duckdb_platform(QUERIES) / "iceberg.duckdb_extension").is_file(),
    reason=f"the pinned DuckDB extensions are not installed in {EXTENSIONS}",
)


def iceberg_table(conn: duckdb.DuckDBPyConnection, folder: Path) -> Path:
    """Writes a one-file Iceberg v2 table and returns its metadata file."""
    (folder / "data").mkdir(parents=True)
    (folder / "metadata").mkdir()
    data, manifest, manifest_list = (
        folder / "data" / "dt=2026-10-21.parquet",
        folder / "metadata" / "m0.avro",
        folder / "metadata" / "snap-1.avro",
    )
    conn.execute(render(TABLE["data"], {"path": Literal(str(data))}))
    conn.execute(
        render(
            TABLE["manifest"],
            {"path": Literal(str(manifest)), "data": Literal(str(data)), "size": Integer(data.stat().st_size)},
        )
    )
    conn.execute(
        render(
            TABLE["manifest list"],
            {
                "path": Literal(str(manifest_list)),
                "manifest": Literal(str(manifest)),
                "size": Integer(manifest.stat().st_size),
            },
        )
    )
    field = {"required": False}
    metadata = {
        "format-version": 2,
        "table-uuid": "019a0000-0000-7000-8000-000000000001",
        "location": str(folder),
        "last-sequence-number": 1,
        "last-updated-ms": 1761004800000,
        "last-column-id": 2,
        "current-schema-id": 0,
        "schemas": [
            {
                "type": "struct",
                "schema-id": 0,
                "fields": [
                    {"id": 1, "name": "dt", "type": "date", **field},
                    {"id": 2, "name": "visits", "type": "long", **field},
                ],
            }
        ],
        "default-spec-id": 0,
        "partition-specs": [
            {"spec-id": 0, "fields": [{"name": "dt", "transform": "identity", "source-id": 1, "field-id": 1000}]}
        ],
        "last-partition-id": 1000,
        "default-sort-order-id": 0,
        "sort-orders": [{"order-id": 0, "fields": []}],
        "properties": {},
        "current-snapshot-id": 1,
        "snapshots": [
            {
                "snapshot-id": 1,
                "sequence-number": 1,
                "timestamp-ms": 1761004800000,
                "manifest-list": str(manifest_list),
                "summary": {"operation": "append"},
                "schema-id": 0,
            }
        ],
        "snapshot-log": [],
        "metadata-log": [],
    }
    path = folder / "metadata" / "v1.metadata.json"
    path.write_text(json.dumps(metadata), encoding="utf-8")
    return path


def config() -> DuckDbConfig:
    return {"extension_directory": str(EXTENSIONS), "autoinstall_known_extensions": False}


def iceberg_tenant(root: Path) -> Path:
    """A tenant folder whose mapping has `dds.visits` over its own Iceberg table and `dds.outside` over a table in a
    folder next to it (like another bucket)."""
    tenant = root / "tenant"
    mapping = tenant / "mapping" / "samovar.duckdb"
    mapping.parent.mkdir(parents=True)
    with duckdb.connect(":memory:", config=config()) as writer:
        writer.execute(render(QUERIES.load_extension, {"name": Identifier("avro")}))
        tables = {
            "visits": iceberg_table(writer, tenant / "warehouse" / "visits"),
            "outside": iceberg_table(writer, root / "other"),
        }
    with duckdb.connect(str(mapping), config=config()) as conn:
        conn.execute(render(QUERIES.load_extension, {"name": Identifier("iceberg")}))
        for name, metadata in tables.items():
            conn.execute(render(TABLE["view"], {"name": Identifier(name), "metadata": Literal(str(metadata))}))
    return tenant


def locked_engine(tenant: Path) -> Engine:
    guard = SqlGuard(SqlParser(QUERIES), lambda: date(2026, 10, 22))
    factory = EngineFactory(QUERIES, EXTENSIONS, EngineLimits("512MB", 1, 30), guard)
    session = DataSession(
        mapping_location=str(tenant / "mapping" / "samovar.duckdb"),
        allowed_directories=(str(tenant) + "/",),
        extensions=("avro", "iceberg"),
        s3=None,
    )
    return factory.open(session)


def test_the_locked_engine_reads_an_iceberg_mapping_view_inside_the_tenant(tmp_path: Path) -> None:
    engine = locked_engine(iceberg_tenant(tmp_path))
    assert engine.settings().locked and not engine.settings().external_access
    result = engine.query(sql("iceberg-day"), 10)
    assert [list(row) for row in result.rows] == [[date(2026, 10, 21), 15]]


def test_an_iceberg_view_over_files_outside_the_tenant_is_refused(tmp_path: Path) -> None:
    with pytest.raises(QueryFailed, match="Permission Error"):
        locked_engine(iceberg_tenant(tmp_path)).query(sql("iceberg-outside"), 10)
