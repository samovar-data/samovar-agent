#!/usr/bin/env python3
"""Shared SQL-text scanner: SQL lives in `.sql` files, never in Python, shell or Dockerfile text.

Repository rule: all SQL text lives in dedicated `.sql` files, never as string literals in code. Run by
`scripts/check`. Standard library only.

What it flags: a string whose text *starts with* a SQL statement of a recognisable shape (SELECT, INSERT, UPDATE,
DELETE, MERGE, VALUES, CREATE, ALTER, DROP, GRANT, REVOKE, TRUNCATE, WITH, SET, RESET, SHOW, LOCK, COPY, VACUUM,
ANALYZE, REFRESH, INSTALL, LOAD, ATTACH, DETACH, PRAGMA, COMMENT ON, DO, CALL, EXPLAIN). Each shape needs the keyword
followed by SQL-looking tokens (for example `DELETE FROM <name> ...`, `SELECT <columns> FROM ...`), so ordinary
English such as "select the tenant" or "update the slug" is not matched.
The ambiguous short keywords (SET, INSTALL, LOAD, ...) match upper-case, or lower-case only in an unmistakable form.

Boolean expressions (not statements) never match any shape, so the scanner needs no special case and has no
allow-list.

Scanned: Python (every string literal, via the AST), shell scripts (`.sh`, `.bash`, `.zsh` or a shebang) and
Dockerfiles. Shell and Dockerfile text is searched at the start of a line (shell only), right after a quote, and in
heredoc bodies, which are treated as one block of text so that a statement split over lines is still recognised.
"""

import ast
import re
import sys
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import NamedTuple

IDENT = r'(?:"[^"]+"|[\w.]+)'
PRIVILEGE = (
    r"(?:all(?:\s+privileges)?|select|insert|update|delete|truncate|references|trigger|usage|create|connect"
    r"|temp(?:orary)?|execute|maintain|set)(?:\s*\([^)]*\))?"
)
OBJECT = (
    r"(?:table|schema|index|role|user|view|function|procedure|trigger|extension|type|sequence|database|policy"
    r"|rule|domain|materialized\s+view|secret|macro)"
)
CREATE_FOLLOW = (
    r"(?:\(|;|$|\b(?:as|on|authorization|with|if|for|from|login|nologin|returns|language|owner|using|inherit"
    r"|nosuperuser|superuser|password|options|server)\b)"
)
ALTER_FOLLOW = (
    r"(?:;|$|\b(?:add|drop|rename|owner|set|reset|with|alter|enable|disable|force|no|inherit|login|nologin"
    r"|password|in|for|grant|revoke|validate|attach|detach|to|nosuperuser|superuser)\b)"
)
DROP_FOLLOW = r"(?:;|$|,|\b(?:cascade|restrict|on)\b)"
SELECT_LIST = r"(?:\*|\{|\(|'|\d+\s*(?:;|,|$|\b(?:as|from)\b)" rf"|{IDENT}\s*(?:,|\(|::|;)|{IDENT}\s+(?:from|as)\b)"


class Shape(NamedTuple):
    name: str
    pattern: re.Pattern[str]


def shape(name: str, pattern: str) -> Shape:
    return Shape(name, re.compile(pattern, re.IGNORECASE | re.DOTALL))


def upper(name: str, pattern: str) -> Shape:
    """A shape whose leading keyword must be upper-case (the keyword is also a common English or shell word)."""
    return Shape(name, re.compile(pattern, re.DOTALL))


SHAPES: tuple[Shape, ...] = (
    shape("SELECT", rf"select\s+(?:(?:all|distinct)\s+)?{SELECT_LIST}"),
    shape(
        "INSERT",
        rf"insert\s+into\s+{IDENT}\s*(?:\(|values\b|select\b|default\s+values\b|;|$)",
    ),
    shape(
        "UPDATE",
        rf"update\s+(?:only\s+)?{IDENT}(?:\s+(?:as\s+)?\w+)?\s+set\s+{IDENT}\s*=",
    ),
    shape(
        "DELETE",
        rf"delete\s+from\s+(?:only\s+)?{IDENT}(?:\s+(?:as\s+)?\w+)?\s*(?:;|$|where\b|using\b|returning\b)",
    ),
    shape(
        "TRUNCATE",
        rf"truncate\s+(?:table\s+)?(?:only\s+)?{IDENT}\s*(?:;|,|$|\b(?:restart|continue|cascade|restrict)\b)",
    ),
    shape(
        "CREATE",
        rf"create\s+(?:or\s+replace\s+)?(?:(?:temp|temporary|persistent|unlogged|unique|global|local)\s+)*{OBJECT}\s+"
        rf"(?:if\s+not\s+exists\s+)?{IDENT}\s*{CREATE_FOLLOW}",
    ),
    shape(
        "CREATE",
        rf"create\s+(?:unique\s+)?index\s+(?:concurrently\s+)?(?:if\s+not\s+exists\s+)?(?:{IDENT}\s+)?on\s+(?:only\s+)?"
        rf"{IDENT}\s*(?:\(|using\b)",
    ),
    shape(
        "CREATE",
        r"create\s+(?:or\s+replace\s+)?(?:(?:persistent|temporary|temp)\s+)?secret\s*\(",
    ),
    shape("MERGE", rf"merge\s+into\s+{IDENT}"),
    shape("VALUES", r"values\s*\(\s*(?:'|\d|null\b)"),
    upper("VALUES", r"VALUES\s*\("),
    upper("SHOW", rf"SHOW\s+(?:ALL|TABLES|DATABASES|SCHEMAS|{IDENT})\s*(?:;|$)"),
    shape(
        "SHOW",
        r"show\s+(?:all|search_path|server_version|tables|databases|schemas|time\s+zone"
        r"|transaction\s+isolation\s+level)\s*(?:;|$)",
    ),
    shape("VACUUM", r"vacuum\s*(?:;|\(|\b(?:full|freeze|verbose|analyze)\b)"),
    upper("VACUUM", rf"VACUUM\s+{IDENT}\s*(?:;|$)"),
    upper("ANALYZE", rf"ANALYZE\s+(?:VERBOSE\s+)?{IDENT}\s*(?:\([^)]*\)\s*)?(?:;|$)"),
    # Lower-case with a qualified name needs the terminating `;`: "analyze report.json" is prose, not a statement.
    shape("ANALYZE", r"analyze\s*;|analyze\s+(?:verbose\s+)?\w+\.\w+\s*;"),
    shape("REFRESH", r"refresh\s+materialized\s+view\b"),
    upper("RESET", rf"RESET\s+(?:ALL|SESSION\s+AUTHORIZATION|{IDENT})\s*(?:;|$)"),
    shape(
        "RESET",
        r"reset\s+(?:all|search_path|role|statement_timeout|lock_timeout|session\s+authorization)\s*(?:;|$)",
    ),
    shape("PRAGMA", r"pragma\s+[\w.]+\s*(?:;|=|\(|$)"),
    upper("DETACH", rf"DETACH\s+(?:DATABASE\s+)?(?:IF\s+EXISTS\s+)?{IDENT}\s*(?:;|$)"),
    shape("DETACH", rf"detach\s+database\s+(?:if\s+exists\s+)?{IDENT}"),
    shape("INSTALL", r"(?:force\s+)?install\s+(?:'[^']+'|\w+)\s*;"),
    shape("LOAD", r"load\s+(?:'[^']+'|\w+)\s*;"),
    shape("ALTER", rf"alter\s+{OBJECT}\s+(?:if\s+exists\s+)?{IDENT}\s*{ALTER_FOLLOW}"),
    shape("ALTER", r"alter\s+(?:default\s+privileges|system\s+set)\b"),
    shape("DROP", rf"drop\s+{OBJECT}\s+(?:if\s+exists\s+)?{IDENT}\s*{DROP_FOLLOW}"),
    shape("DROP", r"drop\s+owned\s+by\b"),
    shape(
        "GRANT",
        rf"(?:grant|revoke)\s+(?:grant\s+option\s+for\s+)?{PRIVILEGE}(?:\s*,\s*{PRIVILEGE})*\s+on\b",
    ),
    upper(
        "GRANT",
        rf"(?:GRANT|REVOKE)\s+{IDENT}\s+(?:TO|FROM)\s+{IDENT}\s*(?:;|$|WITH\b|GRANTED\b)",
    ),
    shape(
        "WITH",
        rf"with\s+(?:recursive\s+)?{IDENT}\s*(?:\([^)]*\)\s*)?as\s*(?:(?:not\s+)?materialized\s*)?\(",
    ),
    upper(
        "SET",
        rf"SET\s+(?:(?:SESSION|LOCAL)\s+)?(?:TIME\s+ZONE\b|ROLE\s+\S|{IDENT}\s*(?:=|TO\b))",
    ),
    shape(
        "SET",
        r"set\s+(?:(?:session|local)\s+)?(?:search_path|statement_timeout|lock_timeout|time\s+zone)\b",
    ),
    shape(
        "LOCK",
        rf"lock\s+(?:table\s+(?:only\s+)?{IDENT}|{IDENT}\s+in\s+[a-z ]+\s+mode\b)",
    ),
    shape(
        "COPY",
        rf"copy\s+(?:{IDENT}\s*(?:\([^)]*\))?|\([^)]*\))\s+(?:from|to)\s+(?:stdin|stdout|program\b|')",
    ),
    upper("INSTALL", r"INSTALL\s+\w+(?:\s+FROM\s+\w+)?\s*(?:;|'|\"|$)"),
    shape("INSTALL", r"install\s+\w+\s+from\s+(?:core|community|nightly|')"),
    upper("LOAD", r"LOAD\s+\w+\s*(?:;|'|\"|$)"),
    shape("ATTACH", r"attach\s+(?:database\s+|if\s+not\s+exists\s+)?'"),
    upper("ATTACH", rf"ATTACH\s+{IDENT}\s+AS\s+\w+"),
    shape("COMMENT", rf"comment\s+on\s+{OBJECT}\s+{IDENT}"),
    shape("DO", r"do\s+(?:language\s+\w+\s+)?(?:\$\w*\$|')"),
    shape("CALL", rf"call\s+{IDENT}\s*\("),
    shape(
        "EXPLAIN",
        r"explain\s+(?:(?:\([^)]*\)|analyze|verbose)\s+)*(?:select|insert|update|delete|with|values|create|execute)\b",
    ),
)

# Skipped at any depth: tool caches and environments only. A package named `docs` or `certs` deeper down is code.
SKIPPED_DIRECTORIES = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
        ".local",
        ".pytest_cache",
        ".mypy_cache",
        "node_modules",
        ".fixture",
    }
)
# Skipped only directly under the repository root (none in this repository).
ROOT_SKIPPED_DIRECTORIES: frozenset[str] = frozenset()
PROJECTS = ("server",)
EXTRA_ROOTS = ("scripts",)
SHELL_SUFFIXES = frozenset({".sh", ".bash", ".zsh"})
# `(?<!<)` excludes here-strings (`<<<`); arithmetic such as `$((1<<2))` is removed first (ARITHMETIC).
HEREDOC = re.compile(r"(?<!<)<<-?\s*(?:\\?(\w+)|'(\w+)'|\"(\w+)\")")
ARITHMETIC = re.compile(r"\$?\(\(.*?\)\)")
LEADING_NOISE = re.compile(r"(?:\s+|--[^\n]*(?:\n|$)|/\*.*?\*/)*", re.DOTALL)
QUOTES = "\"'"


class Finding(NamedTuple):
    path: Path
    line: int
    kind: str
    text: str

    def render(self, root: Path) -> str:
        try:
            shown = self.path.relative_to(root)
        except ValueError:
            shown = self.path
        return f"{shown}:{self.line}: {self.kind} statement text: {self.text!r}"


def statement_at_start(text: str) -> str | None:
    """The kind of SQL statement `text` starts with (after whitespace and SQL comments), if any."""
    noise = LEADING_NOISE.match(text)
    body = text[noise.end() :] if noise else text
    for candidate in SHAPES:
        if candidate.pattern.match(body):
            return candidate.name
    return None


def snippet(text: str) -> str:
    return " ".join(text.split())[:60]


def python_findings(source: str, path: Path) -> list[Finding]:
    tree = ast.parse(source, filename=str(path))
    nested = {id(part) for node in ast.walk(tree) if isinstance(node, ast.JoinedStr) for part in node.values}
    found: list[Finding] = []
    for node in ast.walk(tree):
        text: str | None = None
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in nested:
            text = node.value
        elif isinstance(node, ast.JoinedStr):
            text = "".join(
                (part.value if isinstance(part, ast.Constant) and isinstance(part.value, str) else "{}")
                for part in node.values
            )
        if not isinstance(node, (ast.Constant, ast.JoinedStr)) or text is None:
            continue
        kind = statement_at_start(text)
        if kind is not None:
            found.append(Finding(path, node.lineno, kind, snippet(text)))
    return found


def line_starts(line: str, *, anchor_line_start: bool) -> Iterator[str]:
    """Texts in a shell or Dockerfile line where SQL could begin: the line itself (shell only) and each quoted run."""
    if anchor_line_start:
        yield line
    for index, char in enumerate(line):
        if char in QUOTES:
            rest = line[index + 1 :]
            end = rest.find(char)
            yield rest if end < 0 else rest[:end]


def heredoc_delimiter(line: str) -> str | None:
    match = HEREDOC.search(ARITHMETIC.sub("", line))
    return next((group for group in match.groups() if group), None) if match else None


def block_starts(lines: Sequence[str]) -> Iterator[tuple[int, str]]:
    """Every suffix of a heredoc body as one block of text (so a statement may span lines), then the single line
    (so an end-anchored shape such as `VACUUM;` matches before the next line), each with the offset of its first line.
    """
    for offset in range(len(lines)):
        yield offset, "\n".join(lines[offset:])
        yield offset, lines[offset]


def text_findings(source: str, path: Path, *, shell: bool) -> list[Finding]:
    found: list[Finding] = []
    lines = source.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        number = index + 1
        index += 1
        delimiter = heredoc_delimiter(line) if not line.lstrip().startswith("#") else None
        end = (
            next(
                (i for i in range(index, len(lines)) if lines[i].strip() == delimiter),
                None,
            )
            if delimiter
            else None
        )
        if end is not None:  # without a terminator line `<<` is not a heredoc (for example inside a quoted string)
            body = lines[index:end]
            for offset, block in block_starts(body):
                kind = statement_at_start(block.lstrip())
                if kind is not None:
                    found.append(Finding(path, index + offset + 1, kind, snippet(block)))
                    break
            index = min(end + 1, len(lines))
        if line.lstrip().startswith("#"):
            continue
        for candidate in line_starts(line, anchor_line_start=shell):
            kind = statement_at_start(candidate)
            if kind is not None:
                found.append(Finding(path, number, kind, snippet(candidate)))
                break
    return found


def file_kind(path: Path) -> str | None:
    if path.suffix == ".py":
        return "python"
    if path.name.startswith("Dockerfile"):
        return "dockerfile"
    if path.suffix in SHELL_SUFFIXES:
        return "shell"
    if path.suffix == "":
        with path.open("rb") as handle:
            first = handle.readline(200)
        if first.startswith(b"#!") and re.search(rb"\b(?:ba|z|da)?sh\b", first):
            return "shell"
    return None


def scan_file(path: Path) -> list[Finding]:
    kind = file_kind(path)
    if kind is None:
        return []
    source = path.read_text(encoding="utf-8")
    if kind == "python":
        return python_findings(source, path)
    return text_findings(source, path, shell=kind == "shell")


def candidate_files(roots: Iterable[Path], repo: Path | None = None) -> Iterator[Path]:
    for root in roots:
        if root.is_file():
            yield root
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or SKIPPED_DIRECTORIES.intersection(path.relative_to(root).parts[:-1]):
                continue
            if repo is not None and is_root_skipped(path, repo):
                continue
            yield path


def is_root_skipped(path: Path, repo: Path) -> bool:
    """True for files under `<repo>/docs`, `<repo>/certs` and the like; same-named directories deeper are scanned."""
    try:
        parts = path.relative_to(repo).parts
    except ValueError:
        return False
    return len(parts) > 1 and parts[0] in ROOT_SKIPPED_DIRECTORIES


def default_roots(repo: Path) -> list[Path]:
    return [repo / name for name in (*PROJECTS, *EXTRA_ROOTS) if (repo / name).exists()]


def scan(roots: Iterable[Path], repo: Path | None = None) -> list[Finding]:
    return [finding for path in candidate_files(roots, repo) for finding in scan_file(path)]


def main(argv: list[str]) -> int:
    repo = Path(__file__).resolve().parents[1]
    roots = [Path(argument).resolve() for argument in argv] or default_roots(repo)
    findings = scan(roots, repo)
    for finding in findings:
        print(finding.render(repo), file=sys.stderr)
    if findings:
        print(
            f"{len(findings)} SQL text occurrence(s) outside .sql files (see README, Development).",
            file=sys.stderr,
        )
        return 1
    print("No SQL text outside .sql files.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
