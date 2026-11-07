import gzip
import hashlib
from pathlib import Path

import pytest

from samovar_agent.domain.errors import ExtensionError
from samovar_agent.extensions.installer import ExtensionInstaller
from samovar_agent.extensions.manifest import ExtensionFile, ExtensionManifest
from samovar_agent.ports.http import HttpResponse
from tests.fakes.http import FakeHttpClient

PAYLOAD = b"\x7fELF fake extension"
PACKED = gzip.compress(PAYLOAD, mtime=0)


def manifest(sha256: str = hashlib.sha256(PACKED).hexdigest()) -> ExtensionManifest:
    return ExtensionManifest(
        duckdb_version="v1.5.4",
        base_url="https://extensions.example",
        extensions=["httpfs"],
        files={"osx_arm64": {"httpfs": ExtensionFile(sha256=sha256, size=len(PACKED))}},
    )


def installer(tmp_path: Path, pinned: ExtensionManifest, platform: str = "osx_arm64") -> ExtensionInstaller:
    url = pinned.url("osx_arm64", "httpfs")
    http = FakeHttpClient({("GET", url): HttpResponse(200, PACKED)})
    return ExtensionInstaller(http, pinned, tmp_path, platform, lambda message: None)


def test_verified_extension_is_unpacked_into_the_duckdb_layout(tmp_path: Path) -> None:
    setup = installer(tmp_path, manifest())
    installed = setup.install()
    target = tmp_path / "v1.5.4" / "osx_arm64" / "httpfs.duckdb_extension"
    assert installed[0].path == target and target.read_bytes() == PAYLOAD
    assert [status.installed for status in setup.status()] == [True]


def test_checksum_mismatch_installs_nothing(tmp_path: Path) -> None:
    setup = installer(tmp_path, manifest(sha256="0" * 64))
    with pytest.raises(ExtensionError, match="checksum mismatch"):
        setup.install()
    assert not any(tmp_path.rglob("*.duckdb_extension*"))


def test_unknown_platform_is_refused_before_any_download(tmp_path: Path) -> None:
    with pytest.raises(ExtensionError, match="not supported"):
        installer(tmp_path, manifest(), platform="freebsd_amd64").install()


def test_pinned_manifest_covers_all_supported_platforms_and_extensions() -> None:
    pinned = ExtensionManifest.load()
    assert pinned.duckdb_version == "v1.5.4"
    assert set(pinned.files) == {
        "osx_arm64",
        "osx_amd64",
        "linux_amd64",
        "linux_arm64",
        "windows_amd64",
    }
    for files in pinned.files.values():
        assert set(files) == set(pinned.extensions) == {"httpfs", "avro", "iceberg"}
        assert all(len(item.sha256) == 64 for item in files.values())


def test_incomplete_manifest_is_an_extension_error(tmp_path: Path) -> None:
    pinned = manifest().model_copy(update={"extensions": ["httpfs", "iceberg"]})
    with pytest.raises(ExtensionError, match="no iceberg"):
        installer(tmp_path, pinned).install()


def test_manifest_hashes_must_be_sha256_hex() -> None:
    with pytest.raises(ValueError):
        ExtensionFile(sha256="not-a-hash", size=1)
