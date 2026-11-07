"""Tests of the repository checks (standard library unittest, run by scripts/check)."""

import tempfile
import unittest
from pathlib import Path

from init_check import non_empty_inits
from sql_scan import scan, statement_at_start


def samples() -> list[tuple[str, str]]:
    """Statements in sql/samples.sql, each after a `-- case: <KIND>` line (SQL text stays out of Python)."""
    found: list[tuple[str, str]] = []
    for line in (Path(__file__).parent / "sql" / "samples.sql").read_text(encoding="utf-8").splitlines():
        if line.startswith("-- case:"):
            found.append((line.removeprefix("-- case:").strip(), ""))
        elif found and line.strip():
            found[-1] = (found[-1][0], line.strip())
    return found


class SqlScanTest(unittest.TestCase):
    def test_sql_statement_literals_in_python_are_found(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "module.py"
            statement = next(text for kind, text in samples() if kind == "ATTACH")
            path.write_text(f"QUERY = {statement!r}\nTEXT = 'select the table to describe'\n")
            findings = scan([Path(folder)])
        self.assertEqual([(finding.line, finding.kind) for finding in findings], [(1, "ATTACH")])

    def test_duckdb_statements_and_prose_are_told_apart(self) -> None:
        for kind, statement in samples():
            self.assertEqual(statement_at_start(statement), kind)
        self.assertIsNone(statement_at_start("install the extensions with samovar-agent setup"))
        self.assertIsNone(statement_at_start("sum(visits)"))


class InitCheckTest(unittest.TestCase):
    def test_non_empty_init_files_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "a").mkdir()
            (root / "a" / "__init__.py").write_text("")
            (root / "b").mkdir()
            (root / "b" / "__init__.py").write_text("x = 1\n")
            self.assertEqual(non_empty_inits([root]), [root / "b" / "__init__.py"])


if __name__ == "__main__":
    unittest.main()
