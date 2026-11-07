"""Fills `{{name}}` placeholders of a `.sql` template with typed parts; values are quoted, never pasted raw.

DuckDB has no bind parameters for SET, CREATE SECRET or ATTACH, so these statements are rendered from typed parts.
The one raw insertion is `Statement`, used only for a user query that the guard has already accepted.
"""

import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass

from samovar_agent.domain.errors import SamovarError

PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")
PLAIN_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")


class SqlTemplateError(SamovarError):
    """A template value is missing or malformed (a programming error, never user input)."""


class SqlPart(ABC):
    """A typed template value; each kind knows how to render itself as SQL text."""

    @abstractmethod
    def render(self) -> str: ...


def quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@dataclass(frozen=True)
class Literal(SqlPart):
    value: str

    def render(self) -> str:
        return quote_literal(self.value)


@dataclass(frozen=True)
class Identifier(SqlPart):
    value: str

    def render(self) -> str:
        if not PLAIN_IDENTIFIER.match(self.value):
            raise SqlTemplateError(f"bad identifier {self.value!r}")
        return self.value


@dataclass(frozen=True)
class Integer(SqlPart):
    value: int

    def render(self) -> str:
        return str(int(self.value))


@dataclass(frozen=True)
class Boolean(SqlPart):
    value: bool

    def render(self) -> str:
        return "true" if self.value else "false"


@dataclass(frozen=True)
class LiteralList(SqlPart):
    values: tuple[str, ...]

    def render(self) -> str:
        return "[" + ", ".join(quote_literal(value) for value in self.values) + "]"


@dataclass(frozen=True)
class Statement(SqlPart):
    """A user statement already accepted by the SQL guard."""

    text: str

    def render(self) -> str:
        return self.text


def render(template: str, values: Mapping[str, SqlPart]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            raise SqlTemplateError(f"missing SQL value {name}")
        return values[name].render()

    return PLACEHOLDER.sub(replace, template)


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


@dataclass(frozen=True)
class TextCasts(SqlPart):
    """`CAST("c" AS VARCHAR) AS "c", ...` for a SELECT * REPLACE list (columns named by the query's own result)."""

    columns: tuple[str, ...]

    def render(self) -> str:
        return ", ".join(
            f"CAST({quote_identifier(name)} AS VARCHAR) AS {quote_identifier(name)}" for name in self.columns
        )


@dataclass(frozen=True)
class LiteralStruct(SqlPart):
    """A struct of string literals, e.g. the `columns` argument of read_json: {'name': 'VARCHAR', ...}."""

    items: tuple[tuple[str, str], ...]

    def render(self) -> str:
        return "{" + ", ".join(f"{quote_literal(key)}: {quote_literal(value)}" for key, value in self.items) + "}"
