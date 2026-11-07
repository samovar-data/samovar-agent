"""The data catalog: what each client table means, as the platform publishes it at `GET /api/v1/catalog` (the same
document the cabinet reads). Only the fields the agent uses are modelled; anything else in the document is ignored,
so additive platform changes do not break the plugin.

These models are the single source of `spec/catalog.schema.json` (generated, see `samovar_dev.schemas`).
"""

import hashlib
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

DATE_COLUMN = "dt"


class Lenient(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", validate_by_name=True, validate_by_alias=True)


class LayerId(StrEnum):
    DDS = "dds"
    MART = "mart"


class Source(Lenient):
    code: str = Field(description="Connector code, e.g. yandex_metrika_logs_api or amocrm.")
    title: str
    connector_version: int


class Layer(Lenient):
    id: LayerId
    title: str
    schema_name: str = Field(alias="schema", description="SQL schema of the layer's views.")
    summary: str


class Excluded(Lenient):
    what: str
    why: str


class Column(Lenient):
    name: str
    type: str = Field(description="DuckDB type of the view column.")
    api: str | None = Field(default=None, description="Field of the source API, if the column maps to one.")
    group: str | None = None
    description: str
    example: str | None = Field(default=None, description="Synthetic example value, never real data.")


class Table(Lenient):
    id: str
    layer: LayerId
    view: str = Field(description="Qualified view name, <schema>.<name>.")
    source_code: str
    entity: str
    title: str
    purpose: str
    grain: str
    key: list[str]
    partition: list[str]
    day_rule: str = Field(description="What the day column means, including its timezone.")
    notes: list[str]
    tags: list[str] = []
    fields: list[Column]

    @property
    def date_column(self) -> str | None:
        """The day column of period filters: the partition day."""
        return DATE_COLUMN if DATE_COLUMN in self.partition else None


class Catalog(Lenient):
    sources: list[Source]
    layers: list[Layer]
    groups: dict[str, str]
    excluded: list[Excluded]
    tables: list[Table]

    @property
    def catalog_version(self) -> str:
        """The published catalog carries no version: a short hash of what the agent read stands in for one."""
        return hashlib.sha256(self.model_dump_json().encode("utf-8")).hexdigest()[:12]

    def table(self, ref: str) -> Table | None:
        """A table by id or by qualified view name."""
        return next((table for table in self.tables if ref in (table.id, table.view)), None)

    def views(self) -> frozenset[str]:
        return frozenset(table.view for table in self.tables)
