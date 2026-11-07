"""DuckDB connection settings and the fail-fast checks of their resolved values (phone-home and isolation rule).

DuckDB must never fetch extensions on its own: autoinstall/autoload are off, community and unsigned extensions are
refused, and both extension repositories point at the local folder filled by `samovar-agent setup`.
"""

from dataclasses import dataclass
from pathlib import Path

from samovar_agent.domain.errors import LockdownError

DUCKDB_VERSION = "v1.5.4"
DuckDbConfig = dict[str, str | bool | int | float | list[str]]


@dataclass(frozen=True)
class Resolved:
    version: str
    autoinstall: bool
    autoload: bool
    community: bool
    unsigned: bool
    persistent_secrets: bool
    repository: str
    auto_repository: str
    extension_directory: str
    external_access: bool
    locked: bool


def connection_config(extension_dir: Path, memory_limit: str, threads: int) -> DuckDbConfig:
    repository = str(extension_dir)
    return {
        "autoinstall_known_extensions": False,
        "autoload_known_extensions": False,
        "allow_community_extensions": False,
        "allow_unsigned_extensions": False,
        "allow_persistent_secrets": False,
        "extension_directory": repository,
        "custom_extension_repository": repository,
        "autoinstall_extension_repository": repository,
        "memory_limit": memory_limit,
        "threads": threads,
        "max_temp_directory_size": "0B",
    }


def locked_parser_config() -> DuckDbConfig:
    return {
        "autoinstall_known_extensions": False,
        "autoload_known_extensions": False,
        "allow_community_extensions": False,
        "allow_persistent_secrets": False,
        "enable_external_access": False,
        "lock_configuration": True,
        "threads": 1,
        "memory_limit": "64MB",
    }


def assert_bootstrap(settings: Resolved, extension_dir: Path) -> None:
    if settings.version != DUCKDB_VERSION:
        raise LockdownError(f"unexpected DuckDB {settings.version}, expected {DUCKDB_VERSION}")
    if settings.autoinstall or settings.autoload:
        raise LockdownError("extension autoinstall/autoload is on")
    if settings.community or settings.unsigned:
        raise LockdownError("community or unsigned extensions are allowed")
    if settings.persistent_secrets:
        raise LockdownError("persistent secrets are allowed: stored secrets of the user could be picked up")
    expected = str(extension_dir)
    if {
        settings.repository,
        settings.auto_repository,
        settings.extension_directory,
    } != {expected}:
        raise LockdownError("extension repository is not the local extension folder")


def assert_locked(settings: Resolved) -> None:
    if settings.external_access or not settings.locked:
        raise LockdownError("configuration lock was not applied")
    if settings.autoinstall or settings.autoload:
        raise LockdownError("extension autoinstall/autoload is on")
