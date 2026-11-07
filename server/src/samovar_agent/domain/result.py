"""A stored query result: what make_chart and export work from."""

from dataclasses import dataclass
from datetime import datetime

from samovar_agent.domain.values import JsonValue


@dataclass(frozen=True)
class StoredResult:
    query_id: str
    sql: str
    purpose: str
    columns: tuple[tuple[str, str], ...]
    rows: tuple[tuple[JsonValue, ...], ...]
    truncated: bool
    catalog_version: str
    created_at: datetime

    def column_names(self) -> list[str]:
        return [name for name, _ in self.columns]
