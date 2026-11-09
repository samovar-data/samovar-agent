"""Keeps one engine open over the tenant's data, opened on first use and again when the data's day changes (the demo
snapshot's dates are shifted for the day it was opened on)."""

from collections.abc import Callable
from datetime import date

from samovar_agent.domain.session import DataSession
from samovar_agent.engine.duckdb_engine import Engine, EngineFactory
from samovar_agent.ports.session import DataSessionProvider


class DataAccess:
    def __init__(self, sessions: DataSessionProvider, engines: EngineFactory, today: Callable[[], date]) -> None:
        self._sessions = sessions
        self._engines = engines
        self._today = today
        self._session: DataSession | None = None
        self._engine: Engine | None = None
        self._opened_on: date | None = None

    @property
    def mode(self) -> str:
        return self._sessions.mode

    def problem(self) -> str | None:
        return self._sessions.problem()

    @property
    def session(self) -> DataSession | None:
        return self._session

    def engine(self) -> Engine:
        today = self._today()
        if self._engine is not None and self._opened_on != today:
            self._engine.close()
            self._engine = None
        if self._engine is None:
            session = self._sessions.open()
            self._session = session
            self._engine = self._engines.open(session)
            self._opened_on = today
        return self._engine

    def secrets(self) -> tuple[str, ...]:
        return self._session.secrets() if self._session else ()
