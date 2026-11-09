"""A tiny stand-in for the demo snapshot: the same shape (a base table and a shifted view), built from test SQL."""

import hashlib
from datetime import date
from pathlib import Path

import duckdb

from samovar_agent.adapters.demo_session import DemoSnapshot
from tests.sql_files import sql


def build_snapshot(folder: Path) -> tuple[DemoSnapshot, bytes]:
    path = folder / "built.duckdb"
    conn = duckdb.connect(str(path))
    conn.execute(sql("demo-snapshot"))
    conn.close()
    body = path.read_bytes()
    digest = hashlib.sha256(body).hexdigest()
    pin = DemoSnapshot(
        base_url="https://samovar-demo.example.org/mapping/",
        anchor=date(2026, 11, 7),
        sha256=digest,
    )
    return pin, body
