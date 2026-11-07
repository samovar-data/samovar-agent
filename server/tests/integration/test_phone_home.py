import pytest
from mcp.server._otel import OpenTelemetryMiddleware

from samovar_agent.composition import Application
from samovar_agent.domain.errors import LockdownError
from samovar_agent.phone_home import assert_no_telemetry


def test_built_server_has_no_telemetry_middleware_and_no_tracer(
    app: Application,
) -> None:
    assert_no_telemetry(app.server)


def test_telemetry_check_fails_fast_when_the_middleware_is_back(
    app: Application,
) -> None:
    app.server.middleware.insert(0, OpenTelemetryMiddleware())
    with pytest.raises(LockdownError, match="OpenTelemetry"):
        assert_no_telemetry(app.server)
