"""`samovar-agent setup`: downloads the pinned DuckDB extensions once, checks sha256, unpacks them into the local
extension folder that the engine is locked to. DuckDB itself never downloads anything (autoinstall is off) and
LOAD still checks the extension signature (unsigned extensions are refused)."""

import gzip
import hashlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from samovar_agent.domain.errors import ExtensionError
from samovar_agent.domain.tools import ExtensionStatus
from samovar_agent.extensions.manifest import ExtensionManifest
from samovar_agent.ports.http import HttpClient

MAX_UNPACKED = 512 * 1024 * 1024


@dataclass(frozen=True)
class Installed:
    name: str
    sha256: str
    size: int
    path: Path


class ExtensionInstaller:
    def __init__(
        self,
        http: HttpClient,
        manifest: ExtensionManifest,
        extension_dir: Path,
        platform: str,
        log: Callable[[str], None],
    ) -> None:
        self._http = http
        self._manifest = manifest
        self._dir = extension_dir
        self._platform = platform
        self._log = log

    def path(self, name: str) -> Path:
        return self._dir / self._manifest.duckdb_version / self._platform / f"{name}.duckdb_extension"

    def status(self) -> list[ExtensionStatus]:
        return [ExtensionStatus(name=name, installed=self.path(name).is_file()) for name in self._manifest.extensions]

    def install(self) -> list[Installed]:
        files = self._manifest.files.get(self._platform)
        if files is None:
            raise ExtensionError(
                f"Platform {self._platform} is not supported; supported: {', '.join(sorted(self._manifest.files))}."
            )
        missing = [name for name in self._manifest.extensions if name not in files]
        if missing:
            raise ExtensionError(f"The extension manifest has no {', '.join(missing)} for {self._platform}.")
        return [self._install_one(name, files[name].sha256, files[name].size) for name in self._manifest.extensions]

    def _install_one(self, name: str, sha256: str, size: int) -> Installed:
        url = self._manifest.url(self._platform, name)
        self._log(f"downloading {url}")
        response = self._http.request("GET", url, {})
        if response.status != 200:
            raise ExtensionError(f"{name}: HTTP {response.status} from the extension host")
        digest = hashlib.sha256(response.body).hexdigest()
        self._log(f"{name}: sha256 {digest} ({len(response.body)} bytes), expected {sha256} ({size} bytes)")
        if digest != sha256 or len(response.body) != size:
            raise ExtensionError(f"{name}: checksum mismatch, the file was not installed")
        target = self.path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        unpacked = gzip.decompress(response.body)
        if len(unpacked) > MAX_UNPACKED:
            raise ExtensionError(f"{name}: unpacked file is unexpectedly large")
        partial = target.with_suffix(".partial")
        partial.write_bytes(unpacked)
        os.replace(partial, target)
        self._log(f"{name}: installed {target}")
        return Installed(name=name, sha256=digest, size=size, path=target)
