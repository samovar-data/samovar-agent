"""Export writers: one function per format, selected from a registry by the requested format."""

import csv
import json
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType

from openpyxl import Workbook  # type: ignore[import-untyped]  # openpyxl ships no type information
from openpyxl.cell import WriteOnlyCell  # type: ignore[import-untyped]  # openpyxl ships no type information

from samovar_agent.domain.tools import ExportFormat
from samovar_agent.domain.values import JsonValue

Rows = Sequence[Sequence[JsonValue]]
Cell = str | int | float | bool | None
Writer = Callable[[Path, Sequence[str], Rows], None]
FORMULA_STARTS = frozenset("=+-@\t\r")
# Characters an XLSX (XML 1.0) cell cannot hold; same set as openpyxl's ILLEGAL_CHARACTERS_RE.
ILLEGAL_XML = re.compile(r"[\000-\010]|[\013-\014]|[\016-\037]")


def write_csv(path: Path, columns: Sequence[str], rows: Rows) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([_inert(name) for name in columns])
        writer.writerows([_inert(_flat(value)) for value in row] for row in rows)


def write_json(path: Path, columns: Sequence[str], rows: Rows) -> None:
    records = [dict(zip(columns, row)) for row in rows]
    path.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")


def write_xlsx(path: Path, columns: Sequence[str], rows: Rows) -> None:
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("data")
    sheet.append([_text_cell(sheet, name) for name in columns])
    for row in rows:
        sheet.append([_cell(sheet, _flat(value)) for value in row])
    workbook.save(path)


def _cell(sheet: object, value: Cell) -> object:
    return _text_cell(sheet, value) if isinstance(value, str) else value


def _text_cell(sheet: object, value: str) -> object:
    """A string cell is always text, so a value like "=HYPERLINK(...)" from page titles never becomes a formula;
    control characters XML cannot hold are dropped instead of failing the whole export."""
    cell = WriteOnlyCell(sheet, value=ILLEGAL_XML.sub("", value))
    cell.data_type = "s"
    return cell


def _inert(value: Cell) -> Cell:
    """CSV opened in a spreadsheet: neutralise text that would start a formula, also after leading blanks
    (OWASP CSV injection)."""
    if isinstance(value, str) and value.lstrip(" ")[:1] in FORMULA_STARTS:
        return "'" + value
    return value


def _flat(value: JsonValue) -> Cell:
    """Spreadsheet cells hold scalars; lists and structs become JSON text."""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value


WRITERS: Mapping[ExportFormat, Writer] = MappingProxyType(
    {ExportFormat.CSV: write_csv, ExportFormat.JSON: write_json, ExportFormat.XLSX: write_xlsx}
)
