"""ChartSpec (what the model asks for) and ChartPayload (what the shared JS module `samovar-chart` draws).

The contract belongs to the samovar-chart library (its `chartspec`, `chart-payload` and `theme` schemas, checked
by `samovar_dev.chart_contract`); these models mirror it for the MCP tool schema. The plugin only validates a spec
against the result and assembles the payload; drawing is the library's job.
"""

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from samovar_agent.domain.theme import Theme


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ChartKind(StrEnum):
    LINE = "line"
    BAR = "bar"
    BARH = "barh"
    AREA = "area"
    SCATTER = "scatter"


class ColumnKind(StrEnum):
    NUMBER = "number"
    TIME = "time"
    TEXT = "text"


class ChartSpec(Frozen):
    kind: ChartKind
    title: str = Field(max_length=200)
    x: str = Field(description="Result column on the x axis (categories for bar charts).")
    y: list[str] = Field(min_length=1, max_length=6, description="Numeric result columns, one series each.")
    series: str | None = Field(
        default=None, description="Optional column whose values split a single y column into several series."
    )
    x_title: str | None = None
    y_title: str | None = None
    stacked: bool = False
    labels: dict[str, Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        default_factory=dict,
        max_length=20,
        description="Human labels by result column name (legend, axes, table header), set by the agent. Without a "
        "label the column name is shown.",
    )


class ChartColumn(Frozen):
    name: str
    type: str = Field(description="DuckDB type of the result column.")
    kind: ColumnKind
    label: str = Field(description="Human label: the agent's label for the column, or the column name.")


class ChartData(Frozen):
    columns: list[ChartColumn]
    rows: list[list[Any]]


class ChartPayload(Frozen):
    spec: ChartSpec
    data: ChartData
    theme: Theme
    footer: str = Field(description="Provenance line: catalog version, query id, time.")
