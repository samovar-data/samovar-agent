"""Keeps one engine open over the tenant's data, opened on first use."""

from samovar_agent.domain.session import DataSession
from samovar_agent.engine.duckdb_engine import Engine, EngineFactory
from samovar_agent.ports.session import DataSessionProvider


class DataAccess:
    def __init__(self, sessions: DataSessionProvider, engines: EngineFactory) -> None:
        self._sessions = sessions
        self._engines = engines
        self._session: DataSession | None = None
        self._engine: Engine | None = None

    @property
    def mode(self) -> str:
        return self._sessions.mode

    def problem(self) -> str | None:
        return self._sessions.problem()

    @property
    def session(self) -> DataSession | None:
        return self._session

    def engine(self) -> Engine:
        if self._engine is None:
            session = self._sessions.open()
            self._session = session
            self._engine = self._engines.open(session)
        return self._engine

    def secrets(self) -> tuple[str, ...]:
        return self._session.secrets() if self._session else ()
