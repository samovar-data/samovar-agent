"""Maintainer tool: builds `samovar_agent/extensions/duckdb-extensions.json` by downloading every pinned extension
once from extensions.duckdb.org and recording its sha256 and size. Run manually, only when DuckDB is re-pinned:

    uv run python -m samovar_dev.extension_manifest > src/samovar_agent/extensions/duckdb-extensions.json
"""

import hashlib
import sys

from samovar_agent.adapters.urllib_http import UrllibHttpClient
from samovar_agent.engine.settings import DUCKDB_VERSION
from samovar_agent.extensions.manifest import ExtensionFile, ExtensionManifest

BASE_URL = "https://extensions.duckdb.org"
PLATFORMS = ("osx_arm64", "osx_amd64", "linux_amd64", "linux_arm64", "windows_amd64")
EXTENSIONS = ["httpfs", "avro", "iceberg"]
MAX_BYTES = 64 * 1024 * 1024


def main() -> int:
    http = UrllibHttpClient(timeout_seconds=120, max_bytes=MAX_BYTES)
    draft = ExtensionManifest(
        duckdb_version=DUCKDB_VERSION,
        base_url=BASE_URL,
        extensions=EXTENSIONS,
        files={},
    )
    files: dict[str, dict[str, ExtensionFile]] = {}
    for platform in PLATFORMS:
        for name in EXTENSIONS:
            url = draft.url(platform, name)
            response = http.request("GET", url, {})
            if response.status != 200:
                print(f"{url}: HTTP {response.status}", file=sys.stderr)
                return 1
            digest = hashlib.sha256(response.body).hexdigest()
            print(f"{digest}  {len(response.body):>9}  {url}", file=sys.stderr)
            files.setdefault(platform, {})[name] = ExtensionFile(sha256=digest, size=len(response.body))
    print(draft.model_copy(update={"files": files}).model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
