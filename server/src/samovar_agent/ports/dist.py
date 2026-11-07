"""Port: reads one file of a published library version (Object Storage, or a local build for development)."""

from typing import Protocol


class DistSource(Protocol):
    @property
    def origin(self) -> str: ...

    def fetch(self, name: str) -> bytes: ...
