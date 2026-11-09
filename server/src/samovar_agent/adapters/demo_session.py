"""DataSession over the public demo snapshot: a DuckDB file of synthetic Samovar Data (a tea shop: Yandex Metrika and
amoCRM) downloaded once over HTTPS, checked against the pinned sha256 before it is used, and cached in the data
folder. The views of the file shift every date by the DuckDB variable `demo_shift_days`, set here so that the last
day of the snapshot is yesterday in the data's timezone. No key, no registration, no S3."""

import hashlib
import os
import tempfile
from datetime import date, timedelta
from importlib import resources
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from samovar_agent.domain.errors import UpstreamError
from samovar_agent.domain.session import DataSession
from samovar_agent.ports.http import HttpClient
from samovar_agent.service.data_day import DataDay
from samovar_agent.settings import DataMode

PIN_FILE = "demo-snapshot.json"
SHA256 = r"^[0-9a-f]{64}$"


class DemoSnapshot(BaseModel):
    """The pinned snapshot; a new snapshot is a new plugin version."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    base_url: str = Field(pattern=r"^https://")
    anchor: date = Field(description="The last day of the data inside the file.")
    sha256: str = Field(pattern=SHA256)

    @property
    def file(self) -> str:
        return self.sha256 + ".duckdb"

    @property
    def url(self) -> str:
        return self.base_url + self.file

    @classmethod
    def load(cls) -> "DemoSnapshot":
        return cls.model_validate_json(resources.files("samovar_agent").joinpath(PIN_FILE).read_text(encoding="utf-8"))


class DemoSessionProvider:
    def __init__(self, snapshot: DemoSnapshot, http: HttpClient, cache_dir: Path, data_day: DataDay) -> None:
        self._snapshot = snapshot
        self._http = http
        self._cache_dir = cache_dir
        self._data_day = data_day

    @property
    def mode(self) -> str:
        return DataMode.DEMO.value

    def problem(self) -> str | None:
        return None  # nothing to configure; a failed download is reported when the data is opened

    def shift_days(self) -> int:
        """Days from the snapshot's last day to yesterday in the data's timezone."""
        return (self._data_day.today() - timedelta(days=1) - self._snapshot.anchor).days

    def open(self) -> DataSession:
        path = self._cache_dir / self._snapshot.file
        if not self._is_pinned(path):
            self._download(path)
        return DataSession(
            mapping_location=str(path),
            allowed_directories=(str(self._cache_dir) + "/",),
            extensions=(),
            s3=None,
            demo_shift_days=self.shift_days(),
        )

    def _is_pinned(self, path: Path) -> bool:
        return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == self._snapshot.sha256

    def _download(self, path: Path) -> None:
        response = self._http.request("GET", self._snapshot.url, {})
        if response.status != 200:
            if response.status == 404:
                raise UpstreamError("The demo snapshot was removed from the storage: update the plugin.")
            raise UpstreamError(f"The demo snapshot is not available (HTTP {response.status}): try again later.")
        if hashlib.sha256(response.body).hexdigest() != self._snapshot.sha256:
            raise UpstreamError("The downloaded demo snapshot does not match its pinned sha256: it was not used.")
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        # A unique temporary name: two sessions starting together must not write the same partial file.
        with tempfile.NamedTemporaryFile(dir=self._cache_dir, suffix=".part", delete=False) as partial:
            partial.write(response.body)
        os.replace(partial.name, path)
