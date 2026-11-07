"""Typed settings, read once from the environment by the composition root (nothing else reads os.environ).

The Claude Code plugin passes `userConfig` values through `.mcp.json` `env`; the S3 key is a pair of `sensitive`
options, so Claude Code keeps it in the OS secure storage (macOS Keychain, ...) and hands it only to this process.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from samovar_agent.domain.errors import ConfigurationError

DEFAULT_API_URL = "https://samovardata.ru"
CATALOG_PATH = "/api/v1/catalog"
# Where a client's S3 key reads its bucket in the cloud (the cabinet shows the same values with the key).
DEFAULT_S3_ENDPOINT = "https://s3.cloud.ru"
DEFAULT_S3_REGION = "ru-central-1"
DEFAULT_S3_URL_STYLE = "vhost"
DEFAULT_TIMEZONE = "Europe/Moscow"
PREFIX = "SAMOVAR_"
UNSUBSTITUTED = "${"


class DataMode(StrEnum):
    PLATFORM = "platform"
    FIXTURE = "fixture"


@dataclass(frozen=True)
class Limits:
    max_rows: int = 500
    export_max_rows: int = 100_000
    timeout_seconds: float = 30.0
    memory_limit: str = "1GB"
    threads: int = 2
    dds_window_days: int = 93
    stored_results: int = 50


@dataclass(frozen=True)
class S3Key:
    """The client's own read-only S3 key from the cabinet (S3 keys), with where it reads."""

    key_id: str = field(repr=False)
    secret: str = field(repr=False)
    bucket: str
    endpoint: str = DEFAULT_S3_ENDPOINT
    region: str = DEFAULT_S3_REGION
    url_style: str = DEFAULT_S3_URL_STYLE


@dataclass(frozen=True)
class Settings:
    catalog_url: str
    timezone_override: str | None
    plugin_root: Path
    data_mode: DataMode
    data_dir: Path
    output_dir: Path
    fixture_dir: Path | None
    chart_dist_dir: Path | None = None
    """A local samovar-chart `dist/` to install from instead of Object Storage (development; still pin-checked)."""
    s3_key: S3Key | None = None
    limits: Limits = field(default_factory=Limits)

    @property
    def extension_dir(self) -> Path:
        return self.data_dir / "ext"

    @property
    def chart_cache_dir(self) -> Path:
        return self.data_dir / "lib"

    @classmethod
    def from_env(cls, env: Mapping[str, str], cwd: Path, home: Path, source_root: Path) -> "Settings":
        """`source_root` is the plugin root of a source checkout, used when SAMOVAR_PLUGIN_ROOT is not set."""

        def get(name: str) -> str | None:
            value = env.get(PREFIX + name, "").strip()
            # An empty plugin option may reach us as the literal reference itself: treat it as unset.
            return None if not value or value.startswith(UNSUBSTITUTED) else value

        try:
            mode = DataMode(get("DATA_MODE") or DataMode.PLATFORM)
        except ValueError as error:
            raise ConfigurationError(f"{PREFIX}DATA_MODE must be one of {[m.value for m in DataMode]}") from error
        fixture = get("FIXTURE_DIR")
        if mode is DataMode.FIXTURE and fixture is None:
            raise ConfigurationError(f"{PREFIX}FIXTURE_DIR is required in fixture mode")
        data_dir = get("DATA_DIR") or env.get("CLAUDE_PLUGIN_DATA", "").strip() or str(home / ".samovar-agent")
        defaults = Limits()
        limits = Limits(
            max_rows=_int(get("MAX_ROWS"), defaults.max_rows, "MAX_ROWS"),
            export_max_rows=_int(get("EXPORT_MAX_ROWS"), defaults.export_max_rows, "EXPORT_MAX_ROWS"),
            timeout_seconds=float(
                _int(
                    get("TIMEOUT_SECONDS"),
                    int(defaults.timeout_seconds),
                    "TIMEOUT_SECONDS",
                )
            ),
            memory_limit=get("MEMORY_LIMIT") or defaults.memory_limit,
            threads=_int(get("THREADS"), defaults.threads, "THREADS"),
            dds_window_days=_int(get("DDS_WINDOW_DAYS"), defaults.dds_window_days, "DDS_WINDOW_DAYS"),
        )
        chart_dist = get("CHART_DIST_DIR")
        root = get("PLUGIN_ROOT")
        return cls(
            catalog_url=get("CATALOG_URL") or (get("API_URL") or DEFAULT_API_URL).rstrip("/") + CATALOG_PATH,
            timezone_override=get("TIMEZONE"),
            plugin_root=cwd / Path(root).expanduser() if root else source_root,
            data_mode=mode,
            data_dir=cwd / Path(data_dir).expanduser(),
            output_dir=cwd / Path(get("OUTPUT_DIR") or "samovar-output").expanduser(),
            fixture_dir=cwd / Path(fixture).expanduser() if fixture else None,
            chart_dist_dir=cwd / Path(chart_dist).expanduser() if chart_dist else None,
            s3_key=_s3_key(get),
            limits=limits,
        )


def _s3_key(get: Callable[[str], str | None]) -> S3Key | None:
    """The key as entered (checked when data is opened, so that the server starts and `status` names the problem)."""
    key_id, secret, bucket = get("S3_KEY_ID"), get("S3_SECRET"), get("S3_BUCKET")
    if not (key_id or secret or bucket):
        return None
    return S3Key(
        key_id=key_id or "",
        secret=secret or "",
        bucket=bucket or "",
        endpoint=(get("S3_ENDPOINT") or DEFAULT_S3_ENDPOINT).rstrip("/"),
        region=get("S3_REGION") or DEFAULT_S3_REGION,
        url_style=get("S3_URL_STYLE") or DEFAULT_S3_URL_STYLE,
    )


def _int(raw: str | None, default: int, name: str) -> int:
    if raw is None:
        return default
    if not raw.isdigit() or int(raw) <= 0:
        raise ConfigurationError(f"{PREFIX}{name} must be a positive integer")
    return int(raw)
