"""The SQL guard: a user statement runs only if DuckDB's own parser sees exactly one SELECT over allowed relations.

`json_serialize_sql()` serializes SELECT statements only, so COPY, ATTACH, PRAGMA, SET, INSTALL, LOAD, DDL and DML
are refused by the parser itself. The tree is then walked to allow only:
- views of the dds/mart schemas (optionally in the `samovar` catalog) that are known to the catalog or
  present in the mapping, and names of the statement's CTEs;
- a short list of table functions that read nothing (range, generate_series, unnest);
- scalar functions except a denylist (environment, settings, secret and variable readers).
Queries over the detail layer (dds) must bound the table's day column with DATE literals in the WHERE of the same
SELECT (computed bounds are refused), and the window between the bounds (or from the start to today) may not exceed
the configured number of days.
"""

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from samovar_agent.domain.errors import QueryRejected
from samovar_agent.engine.parser import SqlParser

Node = dict[str, Any]

QUERY_NODES = frozenset({"SELECT_NODE", "SET_OPERATION_NODE", "RECURSIVE_CTE_NODE", "CTE_NODE"})
TABLE_REFS = frozenset({"BASE_TABLE", "JOIN", "SUBQUERY", "TABLE_FUNCTION", "EMPTY", "EXPRESSION_LIST"})
LOWER = frozenset({"COMPARE_GREATERTHANOREQUALTO", "COMPARE_GREATERTHAN"})
UPPER = frozenset({"COMPARE_LESSTHANOREQUALTO", "COMPARE_LESSTHAN"})
DENIED_FUNCTIONS = frozenset({"getenv", "current_setting", "current_secret", "which_secret", "getvariable"})


@dataclass(frozen=True)
class GuardPolicy:
    window_days: int
    detail_schema: str = "dds"
    schemas: frozenset[str] = frozenset({"dds", "mart"})
    catalog: str = "samovar"
    default_date_column: str = "dt"
    table_functions: frozenset[str] = frozenset({"range", "generate_series", "unnest"})
    denied_functions: frozenset[str] = DENIED_FUNCTIONS
    date_columns: Mapping[str, str] = field(default_factory=dict)
    views: frozenset[str] = frozenset()
    """Known `schema.name` views; empty means any name in the allowed schemas."""


@dataclass(frozen=True)
class AcceptedQuery:
    sql: str
    tables: tuple[str, ...]


@dataclass(frozen=True)
class FromTable:
    schema: str
    name: str
    alias: str

    @property
    def qualifiers(self) -> frozenset[str]:
        return frozenset(filter(None, (self.alias, self.name)))


@dataclass(frozen=True)
class Bounds:
    lower: date | None = None
    upper: date | None = None
    computed: bool = False


class SqlGuard:
    def __init__(self, parser: SqlParser, today: Callable[[], date]) -> None:
        self._parser = parser
        self._today = today

    def check(self, sql: str, policy: GuardPolicy) -> AcceptedQuery:
        text = sql.strip().rstrip(";").strip()
        if not text:
            raise QueryRejected("Empty query.")
        root = self.single_select(text)
        ctes = {str(name) for name in _cte_names(root)}
        tables: list[str] = []
        for node in _walk(root):
            self._check_node(node, ctes, policy, tables)
        for select in (node for node in _walk(root) if node.get("type") == "SELECT_NODE" and "select_list" in node):
            self._check_detail_window(select, policy)
        return AcceptedQuery(sql=text, tables=tuple(dict.fromkeys(tables)))

    def single_select(self, text: str) -> Node:
        """The parse tree of `text` if it is exactly one SELECT statement."""
        tree = self._parser.parse(text)
        if tree.get("error"):
            message = str(tree.get("error_message") or "unparsable statement")
            if message.startswith("Only SELECT"):
                raise QueryRejected("Only read-only SELECT queries are allowed.")
            raise QueryRejected(f"SQL error: {message}")
        statements = tree.get("statements") or []
        if len(statements) != 1:
            raise QueryRejected("Exactly one SELECT statement per call.")
        root: Node = statements[0]["node"]
        return root

    def _check_node(self, node: Node, ctes: set[str], policy: GuardPolicy, tables: list[str]) -> None:
        kind = node.get("type")
        if "modifiers" in node and "class" not in node and kind not in QUERY_NODES:
            raise QueryRejected(f"Statement part {kind} is not allowed.")
        if _is_table_ref(node):
            if kind not in TABLE_REFS:
                raise QueryRejected(f"Table reference {kind} is not allowed.")
            if kind == "BASE_TABLE":
                table = _base_table(node, ctes, policy)
                if table is not None:
                    tables.append(table)
            if kind == "TABLE_FUNCTION":
                name = str(node.get("function", {}).get("function_name", "")).lower()
                if name not in policy.table_functions:
                    raise QueryRejected(
                        f"Table function {name}() is not allowed: read data only through the dds.* and mart.* views."
                    )
        if node.get("class") == "FUNCTION" and str(node.get("function_name", "")).lower() in policy.denied_functions:
            raise QueryRejected(f"Function {node['function_name']}() is not allowed.")

    def _check_detail_window(self, select: Node, policy: GuardPolicy) -> None:
        today = self._today()
        for table in _from_tables(select.get("from_table")):
            if table.schema != policy.detail_schema:
                continue
            view = f"{table.schema}.{table.name}"
            column = policy.date_columns.get(view, policy.default_date_column)
            bounds = _bounds(select.get("where_clause"), column, table.qualifiers)
            if bounds.computed:
                raise QueryRejected(
                    f"Bound {view}.{column} with DATE literals only (computed bounds are not accepted), for example "
                    f"{column} BETWEEN DATE '{today.replace(day=1)}' AND DATE '{today}'. Today is {today}."
                )
            if bounds.lower is None:
                raise QueryRejected(
                    f"Queries over the detail layer must filter {view} by {column} in the WHERE of the same SELECT "
                    f"with DATE literals (for example {column} >= DATE '{today}'); use mart.* for long periods. "
                    f"Today is {today}."
                )
            end = bounds.upper or today
            if (end - bounds.lower).days + 1 > policy.window_days:
                raise QueryRejected(
                    f"The detail-layer window {bounds.lower}..{end} is longer than {policy.window_days} days: "
                    "narrow it or use the daily marts (mart.*)."
                )


def _walk(node: object) -> Iterator[Node]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _cte_names(root: Node) -> Iterator[object]:
    for node in _walk(root):
        cte_map = node.get("cte_map")
        if isinstance(cte_map, dict):
            for entry in cte_map.get("map", []):
                yield entry.get("key")


def _is_table_ref(node: Node) -> bool:
    return "class" not in node and "modifiers" not in node and {"type", "alias", "sample"} <= node.keys()


def _base_table(node: Node, ctes: set[str], policy: GuardPolicy) -> str | None:
    """The qualified view name, or None for a reference to one of the statement's CTEs."""
    catalog = str(node.get("catalog_name") or "")
    schema = str(node.get("schema_name") or "")
    name = str(node.get("table_name") or "")
    if not schema and not catalog and name in ctes:
        return None
    view = f"{schema}.{name}"
    if catalog not in ("", policy.catalog) or schema not in policy.schemas:
        shown = ".".join(part for part in (catalog, schema, name) if part)
        raise QueryRejected(f"Relation {shown} is not allowed: query the dds.* and mart.* views (schema required).")
    if policy.views and view not in policy.views:
        raise QueryRejected(f"Unknown view {view}: use a view listed by describe_data.")
    return view


def _from_tables(ref: object) -> Iterator[FromTable]:
    """Base tables of one FROM clause, through joins but not into subqueries (they are checked on their own)."""
    if not isinstance(ref, dict):
        return
    if ref.get("type") == "BASE_TABLE":
        yield FromTable(
            str(ref.get("schema_name") or ""), str(ref.get("table_name") or ""), str(ref.get("alias") or "")
        )
    elif ref.get("type") == "JOIN":
        yield from _from_tables(ref.get("left"))
        yield from _from_tables(ref.get("right"))


def _bounds(where: object, column: str, qualifiers: frozenset[str]) -> Bounds:
    """Bounds on `column` of one table from the top-level AND conjuncts of a WHERE clause."""
    bounds = Bounds()
    for conjunct in _conjuncts(where):
        kind = conjunct.get("type")
        if kind == "COMPARE_BETWEEN" and _is_column(conjunct.get("input"), column, qualifiers):
            bounds = _narrow(_narrow(bounds, conjunct.get("lower"), lower=True), conjunct.get("upper"), lower=False)
        elif kind == "COMPARE_EQUAL" or kind in LOWER or kind in UPPER:
            left, right = conjunct.get("left"), conjunct.get("right")
            if _is_column(left, column, qualifiers):
                value, flipped = right, False
            elif _is_column(right, column, qualifiers):
                value, flipped = left, True
            else:
                continue
            if kind == "COMPARE_EQUAL" or (kind in LOWER) != flipped:
                bounds = _narrow(bounds, value, lower=True)
            if kind == "COMPARE_EQUAL" or (kind in UPPER) != flipped:
                bounds = _narrow(bounds, value, lower=False)
        elif kind == "COMPARE_IN" and _is_column((conjunct.get("children") or [None])[0], column, qualifiers):
            values = conjunct["children"][1:]
            days = [_literal(value) for value in values]
            if not values or None in days:
                bounds = Bounds(bounds.lower, bounds.upper, computed=True)
            else:
                literal = [day for day in days if day is not None]
                bounds = Bounds(_pick(bounds.lower, min(literal), max), _pick(bounds.upper, max(literal), min))
    return bounds


def _narrow(bounds: Bounds, node: object, lower: bool) -> Bounds:
    day = _literal(node)
    if day is None:
        return Bounds(bounds.lower, bounds.upper, computed=True)
    if lower:
        return Bounds(_pick(bounds.lower, day, max), bounds.upper, bounds.computed)
    return Bounds(bounds.lower, _pick(bounds.upper, day, min), bounds.computed)


def _pick(current: date | None, new: date, choose: Callable[[date, date], date]) -> date:
    return new if current is None else choose(current, new)


def _conjuncts(where: object) -> Iterator[Node]:
    if not isinstance(where, dict):
        return
    if where.get("type") == "CONJUNCTION_AND":
        for child in where.get("children", []):
            yield from _conjuncts(child)
    else:
        yield where


def _is_column(node: object, column: str, qualifiers: frozenset[str]) -> bool:
    """A reference to `column` of this table: unqualified, or qualified by its alias or name."""
    if not isinstance(node, dict) or node.get("class") != "COLUMN_REF":
        return False
    names = node["column_names"]
    return bool(names[-1] == column and (len(names) == 1 or names[-2] in qualifiers))


def _literal(node: object) -> date | None:
    """A literal day: a DATE constant, or a string constant (optionally cast to DATE/TIMESTAMP); else None."""
    if isinstance(node, dict) and node.get("class") == "CAST":
        node = node.get("child")
    if not isinstance(node, dict) or node.get("class") != "CONSTANT":
        return None
    value = node.get("value", {}).get("value")
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.strip()).date()
        except ValueError:
            return None
    if isinstance(value, int) and node["value"]["type"]["id"] == "DATE":
        return date.fromordinal(date(1970, 1, 1).toordinal() + value)
    return None
