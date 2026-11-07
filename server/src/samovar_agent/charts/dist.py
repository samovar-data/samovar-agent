"""The samovar-chart library: a pinned published version (`chart-dist.json`: version, URL, sha256 of its manifest),
downloaded by `samovar-agent setup` into the data folder like the DuckDB extensions, and verified again whenever a
chart is drawn. The plugin keeps no chart code of its own.

The manifest sha256 is the trust anchor: the manifest lists the sha256 of every file of the version."""

import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from samovar_agent.adapters.dist_source import checked_name
from samovar_agent.domain.errors import ConfigurationError, SamovarError, UpstreamError
from samovar_agent.domain.tools import ChartLibraryStatus
from samovar_agent.ports.dist import DistSource

PIN_FILE = "chart-dist.json"
MANIFEST = "manifest.json"
PAYLOAD_SCHEMA = "chart-payload.schema.json"
# The ChartSpec, payload and theme contract this plugin speaks (samovar-chart `SCHEMA_VERSION`).
SUPPORTED_SCHEMA_VERSION = 1
SHA256 = r"^[0-9a-f]{64}$"
# Text that would end or derail an inline <script> element.
INLINE_BREAKERS = re.compile(r"</script|<!--", re.IGNORECASE)


class ChartLibraryMissing(SamovarError):
    """The pinned chart library is not installed (or the installed copy does not match the pin)."""


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class DistPin(Frozen):
    name: str
    version: str
    base_url: str
    manifest_sha256: str = Field(pattern=SHA256)

    @classmethod
    def load(cls) -> "DistPin":
        return cls.model_validate_json(resources.files("samovar_agent.charts").joinpath(PIN_FILE).read_text("utf-8"))


class DistFile(Frozen):
    sha256: str = Field(pattern=SHA256)
    size: int = Field(ge=0)


class DistManifest(Frozen):
    name: str
    version: str
    schema_version: int
    script: str
    global_name: str = Field(alias="global")
    files: dict[str, DistFile]


@dataclass(frozen=True)
class ChartBundle:
    version: str
    schema_version: int
    script: str
    global_name: str
    payload_schema: dict[str, Any]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ChartLibrary:
    def __init__(
        self, pin: DistPin, source: DistSource, cache_dir: Path, setup_hint: str, log: Callable[[str], None]
    ) -> None:
        self._pin = pin
        self._source = source
        self._dir = cache_dir / pin.name / pin.version
        self._hint = setup_hint
        self._log = log

    def status(self) -> ChartLibraryStatus:
        """Installed means: the installed manifest is the pinned one (files are checked again when drawing)."""
        try:
            installed = sha256((self._dir / MANIFEST).read_bytes()) == self._pin.manifest_sha256
        except OSError:
            installed = False
        return ChartLibraryStatus(name=self._pin.name, version=self._pin.version, installed=installed)

    def install(self) -> Path:
        """Downloads the pinned version and verifies every file before anything is written."""
        raw = self._source.fetch(MANIFEST)
        digest = sha256(raw)
        self._log(
            f"{self._pin.name} {self._pin.version}: manifest sha256 {digest}, expected {self._pin.manifest_sha256}"
        )
        if digest != self._pin.manifest_sha256:
            raise UpstreamError(f"{self._source.origin}{MANIFEST} does not match the pinned sha256: nothing installed")
        manifest = self._manifest(raw)
        files = {name: self._source.fetch(name) for name in manifest.files}
        for name, data in files.items():
            if sha256(data) != manifest.files[name].sha256:
                raise UpstreamError(f"{name} does not match its sha256 in the manifest: nothing installed")
            self._log(f"{name}: sha256 {sha256(data)} ok")
        self._dir.mkdir(parents=True, exist_ok=True)
        for name, data in {**files, MANIFEST: raw}.items():  # the manifest last: its presence means complete
            partial = self._dir / (name + ".partial")
            partial.write_bytes(data)
            os.replace(partial, self._dir / name)
        self._log(f"{self._pin.name} {self._pin.version}: installed in {self._dir}")
        return self._dir

    def bundle(self) -> ChartBundle:
        """The installed bundle, verified against the pin and the manifest before every chart (no cache: a copy
        changed on disk after start is caught too; hashing ~0.7 MB is cheap)."""
        missing = ChartLibraryMissing(
            f"Chart library {self._pin.name} {self._pin.version} is not installed: run `{self._hint}`."
        )
        try:
            raw = (self._dir / MANIFEST).read_bytes()
        except OSError as error:
            raise missing from error
        if sha256(raw) != self._pin.manifest_sha256:
            raise ChartLibraryMissing(f"The installed chart library does not match the pin: run `{self._hint}`.")
        manifest = self._manifest(raw)
        if manifest.schema_version != SUPPORTED_SCHEMA_VERSION:
            raise ConfigurationError(
                f"{self._pin.name} {self._pin.version} speaks chart schema {manifest.schema_version}, this plugin "
                f"supports {SUPPORTED_SCHEMA_VERSION}: pin a compatible version"
            )
        texts: dict[str, bytes] = {}
        for name in (manifest.script, PAYLOAD_SCHEMA):
            try:
                data = (self._dir / checked_name(name)).read_bytes()
            except OSError as error:
                raise missing from error
            if name not in manifest.files or sha256(data) != manifest.files[name].sha256:
                raise ChartLibraryMissing(f"Installed {name} does not match its sha256: run `{self._hint}`.")
            texts[name] = data
        script = texts[manifest.script].decode("utf-8")
        if INLINE_BREAKERS.search(script):
            raise ConfigurationError(f"{manifest.script} contains '</script' or '<!--' and cannot be inlined")
        return ChartBundle(
            version=manifest.version,
            schema_version=manifest.schema_version,
            script=script,
            global_name=manifest.global_name,
            payload_schema=json.loads(texts[PAYLOAD_SCHEMA]),
        )

    def _manifest(self, raw: bytes) -> DistManifest:
        try:
            manifest = DistManifest.model_validate_json(raw)
        except ValidationError as error:
            raise UpstreamError(
                f"The chart library manifest is not readable: {error.error_count()} problem(s)"
            ) from error
        if manifest.name != self._pin.name or manifest.version != self._pin.version:
            raise UpstreamError(f"The manifest is for {manifest.name} {manifest.version}, not the pinned version")
        for name in manifest.files:
            checked_name(name)
        return manifest
