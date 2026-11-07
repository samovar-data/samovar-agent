"""Test SQL lives in tests/sql/*.sql (repository rule). A cases file holds several statements, each after a
`-- case: <label>` line."""

from pathlib import Path

SQL_DIR = Path(__file__).parent / "sql"
MARKER = "-- case:"


def sql(name: str) -> str:
    return (SQL_DIR / f"{name}.sql").read_text(encoding="utf-8").strip()


def cases(name: str) -> list[tuple[str, str]]:
    found: list[tuple[str, list[str]]] = []
    for line in (SQL_DIR / f"{name}.sql").read_text(encoding="utf-8").splitlines():
        if line.startswith(MARKER):
            found.append((line.removeprefix(MARKER).strip(), []))
        elif found:
            found[-1][1].append(line)
    return [(label, "\n".join(lines).strip()) for label, lines in found]
