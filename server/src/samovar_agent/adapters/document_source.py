"""Published JSON documents from the public site over HTTPS (default) or a local file (fixtures, offline demo)."""

from pathlib import Path

from pydantic import BaseModel, ValidationError

from samovar_agent.domain.errors import UpstreamError
from samovar_agent.ports.document import DocumentSource
from samovar_agent.ports.http import HttpClient

FILE_SCHEME = "file://"


def parse_document[M: BaseModel](raw: bytes, origin: str, model: type[M]) -> M:
    try:
        return model.model_validate_json(raw)
    except ValidationError as error:
        raise UpstreamError(
            f"The document at {origin} does not match the supported schema "
            f"({error.error_count()} problem(s)); update the plugin or check the URL."
        ) from error


class HttpDocumentSource[M: BaseModel]:
    def __init__(self, http: HttpClient, url: str, model: type[M]) -> None:
        self._http = http
        self._url = url
        self._model = model

    def load(self) -> M:
        response = self._http.request("GET", self._url, {"Accept": "application/json"})
        if response.status != 200:
            raise UpstreamError(f"The document is unavailable: HTTP {response.status} from {self._url}")
        return parse_document(response.body, self._url, self._model)


class FileDocumentSource[M: BaseModel]:
    def __init__(self, path: Path, model: type[M]) -> None:
        self._path = path
        self._model = model

    def load(self) -> M:
        try:
            raw = self._path.read_bytes()
        except OSError as error:
            raise UpstreamError(f"The file {self._path} is unreadable: {type(error).__name__}") from error
        return parse_document(raw, str(self._path), self._model)


def document_source[M: BaseModel](url: str, http: HttpClient, model: type[M]) -> DocumentSource[M]:
    if url.startswith(FILE_SCHEME):
        return FileDocumentSource(Path(url.removeprefix(FILE_SCHEME)), model)
    return HttpDocumentSource(http, url, model)
