"""DataSession over a local fixture tenant (evals, offline demo): a mapping database whose views read local Parquet."""

from pathlib import Path

from samovar_agent.domain.errors import NoDataYet
from samovar_agent.domain.session import DataSession

MAPPING_FILE = "mapping.duckdb"


class FixtureSessionProvider:
    def __init__(self, fixture_dir: Path) -> None:
        self._dir = fixture_dir

    @property
    def mode(self) -> str:
        return "fixture"

    def problem(self) -> str | None:
        return None  # a missing fixture is reported when it is opened

    def open(self) -> DataSession:
        mapping = self._dir / MAPPING_FILE
        if not mapping.is_file():
            raise NoDataYet(
                f"No fixture mapping at {mapping}: build it with "
                "`uv run python -m samovar_dev.tenant_fixture <folder>`."
            )
        return DataSession(
            mapping_location=str(mapping),
            allowed_directories=(str(self._dir) + "/",),
            extensions=(),
            s3=None,
        )
