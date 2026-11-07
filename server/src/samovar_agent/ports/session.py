"""Port: read access to the tenant's data (the client's own S3 key, or a local fixture tenant)."""

from typing import Protocol

from samovar_agent.domain.session import DataSession


class DataSessionProvider(Protocol):
    @property
    def mode(self) -> str: ...

    def problem(self) -> str | None:
        """Why access cannot be opened (a configuration problem), without opening it."""
        ...

    def open(self) -> DataSession: ...
