"""Port to HTTP(S): the platform's public catalog, the DuckDB extension host and the chart library storage."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes


class HttpClient(Protocol):
    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None = None,
    ) -> HttpResponse: ...
