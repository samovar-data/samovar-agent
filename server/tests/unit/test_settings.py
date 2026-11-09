from pathlib import Path

import pytest

from samovar_agent.domain.errors import ConfigurationError
from samovar_agent.settings import DataMode, Settings

HOME = Path("/home/user")
CWD = Path("/work/project")
SOURCE = Path("/src/samovar-agent")


def settings(env: dict[str, str]) -> Settings:
    return Settings.from_env(env, CWD, HOME, SOURCE)


def test_defaults_use_the_public_site_and_the_plugin_data_folder() -> None:
    loaded = settings({"CLAUDE_PLUGIN_DATA": "/plugin/data"})
    assert loaded.catalog_url == "https://samovardata.ru/api/v1/catalog"
    assert loaded.data_mode is DataMode.PLATFORM
    assert loaded.extension_dir == Path("/plugin/data/ext")
    assert loaded.output_dir == CWD / "samovar-output"
    assert loaded.plugin_root == SOURCE and loaded.chart_cache_dir == Path("/plugin/data/lib")
    assert loaded.chart_dist_dir is None
    assert loaded.s3_key is None


def test_the_catalog_follows_the_platform_url_unless_set() -> None:
    assert settings({"SAMOVAR_API_URL": "http://127.0.0.1:8000/"}).catalog_url == "http://127.0.0.1:8000/api/v1/catalog"
    assert settings({"SAMOVAR_CATALOG_URL": "file:///x/catalog.json"}).catalog_url == "file:///x/catalog.json"


def test_plugin_root_comes_from_the_plugin_when_given() -> None:
    assert settings({"SAMOVAR_PLUGIN_ROOT": "/plugins/samovar"}).plugin_root == Path("/plugins/samovar")


def test_a_local_chart_dist_can_replace_the_published_one_for_development() -> None:
    assert settings({"SAMOVAR_CHART_DIST_DIR": "../samovar-chart/dist"}).chart_dist_dir == CWD / "../samovar-chart/dist"


def test_without_plugin_data_the_home_folder_is_used() -> None:
    assert settings({}).data_dir == HOME / ".samovar-agent"


KEY = {"SAMOVAR_S3_KEY_ID": "KEYID0123", "SAMOVAR_S3_SECRET": "secret-value-0123", "SAMOVAR_S3_BUCKET": "samovar-t-a1"}


def test_the_s3_key_defaults_to_the_cloud_storage_and_is_kept_out_of_repr() -> None:
    key = settings(KEY).s3_key
    assert key is not None and (key.bucket, key.endpoint, key.region, key.url_style) == (
        "samovar-t-a1",
        "https://s3.cloud.ru",
        "ru-central-1",
        "vhost",
    )
    assert "secret-value-0123" not in repr(settings(KEY)) and "KEYID0123" not in repr(settings(KEY))


def test_a_local_storage_can_be_given_for_the_dev_stand() -> None:
    env = {**KEY, "SAMOVAR_S3_ENDPOINT": "http://127.0.0.1:9000/", "SAMOVAR_S3_URL_STYLE": "path"}
    key = settings(env).s3_key
    assert key is not None and (key.endpoint, key.url_style) == ("http://127.0.0.1:9000", "path")


def test_an_incomplete_s3_key_still_loads_so_that_the_server_starts() -> None:
    key = settings({**KEY, "SAMOVAR_S3_BUCKET": ""}).s3_key
    assert key is not None and key.bucket == ""


def test_an_unsubstituted_plugin_option_counts_as_unset() -> None:
    loaded = settings(
        {
            "SAMOVAR_S3_KEY_ID": "${user_config.s3_key_id}",
            "SAMOVAR_S3_SECRET": "${user_config.s3_secret}",
            "SAMOVAR_S3_BUCKET": "${user_config.s3_bucket}",
            "SAMOVAR_OUTPUT_DIR": "${user_config.output_dir}",
        }
    )
    assert loaded.s3_key is None and loaded.output_dir == CWD / "samovar-output"


def test_fixture_mode_requires_a_fixture_folder() -> None:
    with pytest.raises(ConfigurationError, match="FIXTURE_DIR"):
        settings({"SAMOVAR_DATA_MODE": "fixture"})


@pytest.mark.parametrize("value", ["0", "-5", "ten"])
def test_limits_must_be_positive_integers(value: str) -> None:
    with pytest.raises(ConfigurationError, match="MAX_ROWS"):
        settings({"SAMOVAR_MAX_ROWS": value})


def test_unknown_data_mode_is_a_configuration_error() -> None:
    with pytest.raises(ConfigurationError, match="DATA_MODE"):
        settings({"SAMOVAR_DATA_MODE": "cloud"})


def test_timezone_is_only_an_override() -> None:
    assert settings({}).timezone_override is None
    assert settings({"SAMOVAR_TIMEZONE": "Asia/Yekaterinburg"}).timezone_override == "Asia/Yekaterinburg"


def test_demo_mode_is_chosen_explicitly_and_needs_no_key() -> None:
    loaded = settings({"SAMOVAR_DATA_MODE": "demo"})
    assert loaded.data_mode is DataMode.DEMO and loaded.s3_key is None
    assert loaded.demo_dir == loaded.data_dir / "demo"


def test_an_empty_key_does_not_switch_to_demo_and_an_unsubstituted_option_means_platform() -> None:
    assert settings({}).data_mode is DataMode.PLATFORM
    assert settings({"SAMOVAR_DATA_MODE": "${user_config.data_mode}"}).data_mode is DataMode.PLATFORM
