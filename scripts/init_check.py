#!/usr/bin/env python3
"""Shared check: every `__init__.py` under `server/` and `scripts/` is empty (0 bytes).

Repository rule: `__init__.py` files contain nothing (no code, re-exports or docstrings); every class and function
lives in a named module. Run by `scripts/check`. Standard library only. Virtual environments and tool caches are
skipped.
"""

import sys
from pathlib import Path

PROJECTS = ("server", "scripts")
SKIPPED_DIRECTORIES = frozenset(
    {
        ".venv",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        "node_modules",
        "build",
        "dist",
    }
)


def non_empty_inits(roots: list[Path]) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        for path in sorted(root.rglob("__init__.py")):
            if SKIPPED_DIRECTORIES.isdisjoint(path.relative_to(root).parts) and path.stat().st_size > 0:
                found.append(path)
    return found


def main(argv: list[str]) -> int:
    repo = Path(__file__).resolve().parents[1]
    roots = [Path(argument).resolve() for argument in argv] or [repo / project for project in PROJECTS]
    findings = non_empty_inits(roots)
    for path in findings:
        print(f"{path}: __init__.py must be empty (0 bytes)", file=sys.stderr)
    if findings:
        print(
            f"{len(findings)} non-empty __init__.py file(s) (see README, Development).",
            file=sys.stderr,
        )
        return 1
    print("All __init__.py files are empty.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
