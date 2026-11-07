"""HttpClient over the standard library (no extra dependency).

Only https (or http to a loopback host) is accepted, and redirects are never followed: urllib would otherwise copy
headers such as Authorization to whatever host and scheme the Location names. A 3xx answer is an UpstreamError.
Headers are added as "unredirected" as a second line of defence.
"""

import urllib.error
import urllib.request
from collections.abc import Mapping
from email.message import Message
from http.client import HTTPResponse
from typing import IO
from urllib.parse import urlsplit

from samovar_agent.domain.errors import ConfigurationError, UpstreamError
from samovar_agent.ports.http import HttpResponse

LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
USER_AGENT = "samovar-agent"


class RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> urllib.request.Request | None:
        return None  # urllib then raises HTTPError with the 3xx code


def check_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https" and not (parts.scheme == "http" and parts.hostname in LOOPBACK):
        raise ConfigurationError(f"Refusing a non-HTTPS URL: {parts.scheme}://{parts.hostname}")


class UrllibHttpClient:
    def __init__(self, timeout_seconds: float, max_bytes: int) -> None:
        self._timeout = timeout_seconds
        self._max_bytes = max_bytes
        self._opener = urllib.request.build_opener(RefuseRedirects())

    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None = None,
    ) -> HttpResponse:
        check_url(url)
        host = urlsplit(url).hostname
        request = urllib.request.Request(url, data=body, method=method)
        for name, value in {"User-Agent": USER_AGENT, **headers}.items():
            request.add_unredirected_header(name, value)
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                return HttpResponse(status=int(response.status), body=self._read(response))
        except urllib.error.HTTPError as error:
            if 300 <= error.code < 400:
                raise UpstreamError(f"{host} answered with a redirect (HTTP {error.code}); redirects are not followed")
            return HttpResponse(status=int(error.code), body=b"")
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise UpstreamError(f"{host} is unreachable: {type(error).__name__}") from error

    def _read(self, response: HTTPResponse) -> bytes:
        data = response.read(self._max_bytes + 1)
        if len(data) > self._max_bytes:
            raise UpstreamError(f"Response is larger than {self._max_bytes} bytes")
        return data
