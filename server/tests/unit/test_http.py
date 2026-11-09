"""The real stdlib HTTP client against local servers: redirects are refused, so no header is carried to another host."""

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from samovar_agent.adapters.urllib_http import UrllibHttpClient
from samovar_agent.domain.errors import ConfigurationError, UpstreamError

KEY = "redirect-test-token"


class Recorder(BaseHTTPRequestHandler):
    seen: list[dict[str, str]] = []
    location = ""

    def do_GET(self) -> None:
        type(self).seen.append(dict(self.headers))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_POST(self) -> None:
        self.send_response(302)
        self.send_header("Location", type(self).location)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


def serve(handler: type[BaseHTTPRequestHandler]) -> HTTPServer:
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def servers() -> Iterator[tuple[HTTPServer, HTTPServer]]:
    target = serve(type("Target", (Recorder,), {"seen": []}))
    redirector = serve(type("Redirector", (Recorder,), {"location": f"http://127.0.0.1:{target.server_port}/evil"}))
    yield redirector, target
    redirector.shutdown()
    target.shutdown()


def test_redirect_is_refused_and_headers_are_not_sent_on(servers: tuple[HTTPServer, HTTPServer]) -> None:
    redirector, target = servers
    client = UrllibHttpClient(timeout_seconds=5, max_bytes=1000)
    with pytest.raises(UpstreamError, match="redirect"):
        client.request(
            "POST", f"http://127.0.0.1:{redirector.server_port}/api", {"Authorization": f"Bearer {KEY}"}, b""
        )
    assert target.RequestHandlerClass.seen == []  # type: ignore[attr-defined]  # Recorder subclass state


def test_plain_requests_still_work(servers: tuple[HTTPServer, HTTPServer]) -> None:
    _, target = servers
    response = UrllibHttpClient(timeout_seconds=5, max_bytes=1000).request(
        "GET", f"http://127.0.0.1:{target.server_port}/", {}
    )
    assert response.status == 200 and response.body == b"ok"


@pytest.mark.parametrize("url", ["http://samovardata.example/api", "ftp://x.example/", "file:///etc/passwd"])
def test_only_https_or_loopback_http_is_allowed(url: str) -> None:
    with pytest.raises(ConfigurationError, match="non-HTTPS"):
        UrllibHttpClient(timeout_seconds=5, max_bytes=1000).request("GET", url, {})


def test_an_answer_over_the_size_limit_is_an_error_with_the_limit_named(servers: tuple[HTTPServer, HTTPServer]) -> None:
    _, target = servers
    with pytest.raises(UpstreamError, match="larger than 1 bytes"):
        UrllibHttpClient(timeout_seconds=5, max_bytes=1).request("GET", f"http://127.0.0.1:{target.server_port}/", {})
