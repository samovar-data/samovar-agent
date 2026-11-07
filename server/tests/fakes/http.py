"""A scripted HttpClient: answers by (method, url) and records every request."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from samovar_agent.ports.http import HttpResponse


@dataclass(frozen=True)
class Recorded:
    method: str
    url: str
    headers: dict[str, str]
    body: bytes | None


@dataclass
class FakeHttpClient:
    responses: dict[tuple[str, str], HttpResponse] = field(default_factory=dict)
    requests: list[Recorded] = field(default_factory=list)

    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None = None,
    ) -> HttpResponse:
        self.requests.append(Recorded(method, url, dict(headers), body))
        return self.responses.get((method, url), HttpResponse(status=404, body=b""))
