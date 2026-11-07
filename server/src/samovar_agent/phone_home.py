"""Third-party phone-home checks (repository rule), asserted on the resolved state in the composition root.

- DuckDB: no extension autoinstall/autoload, no community/unsigned extensions, repositories = the local folder
  (checked on every engine open, see engine/settings.py).
- MCP SDK 2.x: ships an OpenTelemetry middleware; it is removed from the server, and the OpenTelemetry tracer
  provider must be the API's no-op proxy with no SDK installed, so nothing can export spans.
- openpyxl, pydantic, jsonschema: no network code paths are used. Chart pages inline the pinned samovar-chart
  bundle (no CDN); `setup` is the only step that downloads it.
- uv: contacts the package index only while syncing the frozen lock; it has no telemetry.
"""

from importlib.util import find_spec

from mcp.server.mcpserver import MCPServer
from opentelemetry import trace

from samovar_agent.domain.errors import LockdownError

OTEL_MIDDLEWARE = "OpenTelemetryMiddleware"


def disable_mcp_telemetry(server: MCPServer) -> None:
    server.middleware[:] = [item for item in server.middleware if type(item).__name__ != OTEL_MIDDLEWARE]


def assert_no_telemetry(server: MCPServer) -> None:
    if any(type(item).__name__ == OTEL_MIDDLEWARE for item in server.middleware):
        raise LockdownError("MCP OpenTelemetry middleware is still installed")
    if find_spec("opentelemetry.sdk") is not None:
        raise LockdownError("an OpenTelemetry SDK is installed: spans could be exported")
    provider = trace.get_tracer_provider()
    if not isinstance(provider, (trace.ProxyTracerProvider, trace.NoOpTracerProvider)):
        raise LockdownError(f"an OpenTelemetry tracer provider is configured: {type(provider).__name__}")
