import csv
import json
from pathlib import Path

from openpyxl import load_workbook  # type: ignore[import-untyped]  # openpyxl ships no type information

from samovar_agent.domain.tools import ExportFormat
from samovar_agent.domain.values import JsonValue
from samovar_agent.export.writers import WRITERS

COLUMNS = ["page", "views", "goals"]
ROWS: list[list[JsonValue]] = [['=HYPERLINK("http://x")', 3, [1001, 1002]], ["/catalog", 5, []]]


def test_csv_neutralises_formula_text_and_keeps_numbers(tmp_path: Path) -> None:
    path = tmp_path / "out.csv"
    WRITERS[ExportFormat.CSV](path, COLUMNS, ROWS)
    rows = list(csv.reader(path.open(encoding="utf-8-sig")))
    assert rows[0] == COLUMNS
    assert rows[1][0].startswith("'=") and rows[1][1] == "3" and rows[1][2] == "[1001, 1002]"


def test_json_export_is_a_list_of_records(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    WRITERS[ExportFormat.JSON](path, COLUMNS, ROWS)
    assert json.loads(path.read_text(encoding="utf-8"))[1] == {
        "page": "/catalog",
        "views": 5,
        "goals": [],
    }


def test_xlsx_cells_with_formula_text_stay_text(tmp_path: Path) -> None:
    path = tmp_path / "out.xlsx"
    WRITERS[ExportFormat.XLSX](path, COLUMNS, ROWS)
    sheet = load_workbook(path)["data"]
    assert sheet["A2"].data_type == "s" and sheet["A2"].value == ROWS[0][0]
    assert sheet["B3"].value == 5


def test_csv_neutralises_formulas_hidden_behind_leading_spaces(tmp_path: Path) -> None:
    path = tmp_path / "out.csv"
    WRITERS[ExportFormat.CSV](path, ["v"], [["  =1+1"], ["-5 items"]])
    rows = list(csv.reader(path.open(encoding="utf-8-sig")))
    assert rows[1][0] == "'  =1+1" and rows[2][0] == "'-5 items"


def test_xlsx_drops_control_characters_instead_of_failing(tmp_path: Path) -> None:
    path = tmp_path / "out.xlsx"
    WRITERS[ExportFormat.XLSX](path, ["title"], [["Чайник\x00\x07 тульский"]])
    assert load_workbook(path)["data"]["A2"].value == "Чайник тульский"
