"""Port: loads a published JSON document (the platform's data catalog) as a validated model."""

from typing import Protocol, TypeVar

from pydantic import BaseModel

M = TypeVar("M", bound=BaseModel, covariant=True)


class DocumentSource(Protocol[M]):
    def load(self) -> M: ...
