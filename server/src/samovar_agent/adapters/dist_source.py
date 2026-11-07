"""Sources of the samovar-chart dist: the public Object Storage URL, or a local `dist/` for development."""

from pathlib import Path

from samovar_agent.domain.errors import UpstreamError
from samovar_agent.ports.http import HttpClient

SAFE_NAME = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-._ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def checked_name(name: str) -> str:
    """Only plain file names from the manifest (no paths): a manifest cannot point outside its version."""
    if not name or name.startswith(".") or not set(name) <= SAFE_NAME:
        raise UpstreamError(f"Unexpected file name {name!r} in the chart library manifest")
    return name


class HttpDistSource:
    def __init__(self, http: HttpClient, base_url: str) -> None:
        self._http = http
        self._base = base_url if base_url.endswith("/") else base_url + "/"

    @property
    def origin(self) -> str:
        return self._base

    def fetch(self, name: str) -> bytes:
        url = self._base + checked_name(name)
        response = self._http.request("GET", url, {})
        if response.status != 200:
            raise UpstreamError(f"The chart library file {url} is unavailable: HTTP {response.status}")
        return response.body


class DirectoryDistSource:
    def __init__(self, folder: Path) -> None:
        self._folder = folder

    @property
    def origin(self) -> str:
        return str(self._folder)

    def fetch(self, name: str) -> bytes:
        path = self._folder / checked_name(name)
        try:
            return path.read_bytes()
        except OSError as error:
            raise UpstreamError(f"The chart library file {path} is unreadable: {type(error).__name__}") from error
