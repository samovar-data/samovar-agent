"""A small samovar-chart dist for tests: a stub bundle, the library's payload schema (copied from samovar-chart 0.1.1)
and a manifest with real sha256 values; the pin points at it. No network, no chart logic."""

import hashlib
import json
import shutil
from pathlib import Path

from samovar_agent.charts.dist import DistPin

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "chart-dist"
VERSION = "0.1.1"
SCRIPT = f"samovar-chart-{VERSION}.min.js"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_dist(
    folder: Path, script: bytes | None = None, schema: dict[str, object] | None = None, schema_version: int = 1
) -> DistPin:
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE / SCRIPT, folder / SCRIPT)
    shutil.copy(FIXTURE / "chart-payload.schema.json", folder / "chart-payload.schema.json")
    if script is not None:
        (folder / SCRIPT).write_bytes(script)
    if schema is not None:
        (folder / "chart-payload.schema.json").write_text(json.dumps(schema), encoding="utf-8")
    files = {
        name: {"sha256": sha256((folder / name).read_bytes()), "size": (folder / name).stat().st_size}
        for name in (SCRIPT, "chart-payload.schema.json")
    }
    manifest = {
        "name": "samovar-chart",
        "version": VERSION,
        "schema_version": schema_version,
        "script": SCRIPT,
        "global": "SamovarChart",
        "files": files,
    }
    raw = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    (folder / "manifest.json").write_bytes(raw)
    return DistPin(
        name="samovar-chart",
        version=VERSION,
        base_url="https://static.example/samovar-chart/0.1.1/",
        manifest_sha256=sha256(raw),
    )
