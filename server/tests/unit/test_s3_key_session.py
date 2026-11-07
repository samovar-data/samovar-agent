from dataclasses import replace

import pytest

from samovar_agent.adapters.s3_key_session import S3KeySessionProvider
from samovar_agent.domain.errors import ConfigurationError
from tests.fakes.s3_key import KEY_ID, SECRET, s3_key


def test_the_key_opens_the_mapping_of_its_bucket_like_the_cabinet_connection_file() -> None:
    session = S3KeySessionProvider(s3_key()).open()
    assert session.mapping_location == "s3://samovar-t-demo/mapping/samovar.duckdb"
    assert session.extensions == ("httpfs", "avro", "iceberg")
    assert session.s3 is not None and session.s3.scope == "s3://samovar-t-demo/"
    assert (session.s3.endpoint, session.s3.use_ssl, session.s3.url_style) == ("s3.cloud.ru", True, "vhost")
    assert session.secrets() == (KEY_ID, SECRET)


def test_duckdb_may_read_only_inside_the_clients_bucket() -> None:
    # The folders inside it are limited by the bucket policy of the key, not by the plugin.
    assert S3KeySessionProvider(s3_key()).open().allowed_directories == ("s3://samovar-t-demo/",)


@pytest.mark.parametrize(
    ("endpoint", "host", "ssl"),
    [("http://127.0.0.1:9000", "127.0.0.1:9000", False), ("s3.cloud.ru", "s3.cloud.ru", True)],
)
def test_the_endpoint_scheme_decides_ssl_and_a_bare_host_means_https(endpoint: str, host: str, ssl: bool) -> None:
    s3 = S3KeySessionProvider(s3_key(endpoint)).open().s3
    assert s3 is not None and (s3.endpoint, s3.use_ssl) == (host, ssl)


def test_without_a_key_the_session_says_where_to_get_one() -> None:
    assert "S3 keys" in (S3KeySessionProvider(None).problem() or "")
    with pytest.raises(ConfigurationError, match="S3 keys"):
        S3KeySessionProvider(None).open()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"bucket": ""}, "needs all of"),
        ({"bucket": "s3://samovar-t-demo/mapping/"}, "bucket name"),
        ({"url_style": "virtual"}, "S3_URL_STYLE"),
        ({"endpoint": "http://s3.example.org"}, "non-HTTPS"),
        ({"endpoint": "ftp://s3.example.org"}, "non-HTTPS"),
    ],
)
def test_an_incomplete_or_unsafe_key_is_a_problem_and_opens_nothing(change: dict[str, str], message: str) -> None:
    sessions = S3KeySessionProvider(replace(s3_key(), **change))
    assert message in (sessions.problem() or "")
    with pytest.raises(ConfigurationError, match=message):
        sessions.open()


def test_plain_http_is_allowed_only_to_a_loopback_storage() -> None:
    assert S3KeySessionProvider(s3_key("http://127.0.0.1:9000")).problem() is None


def test_session_repr_hides_credentials() -> None:
    session = S3KeySessionProvider(s3_key()).open()
    assert SECRET not in repr(session) and KEY_ID not in repr(session)
