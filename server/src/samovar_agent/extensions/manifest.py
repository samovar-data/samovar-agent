"""The pinned DuckDB extension manifest (`duckdb-extensions.json`): versions, platforms and sha256 of each file."""

from importlib import resources

from pydantic import BaseModel, ConfigDict, Field

MANIFEST_FILE = "duckdb-extensions.json"


class ExtensionFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(gt=0)


class ExtensionManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    duckdb_version: str
    base_url: str
    extensions: list[str]
    files: dict[str, dict[str, ExtensionFile]]

    def url(self, platform: str, name: str) -> str:
        return f"{self.base_url}/{self.duckdb_version}/{platform}/{name}.duckdb_extension.gz"

    @classmethod
    def load(cls) -> "ExtensionManifest":
        text = resources.files("samovar_agent.extensions").joinpath(MANIFEST_FILE).read_text(encoding="utf-8")
        return cls.model_validate_json(text)
