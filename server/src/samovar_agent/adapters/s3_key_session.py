"""Read access through the client's own read-only S3 key (created by an admin in the cabinet, S3 keys).

The key is a permanent key of the tenant's reader. DuckDB may read anywhere in the client's bucket and nowhere else;
which folders of it the key really reads is the bucket policy's business (the plugin does not depend on the
platform's folder names). The mapping is attached from `s3://<bucket>/mapping/samovar.duckdb`, as in the cabinet's
DuckDB connection file. No platform call is made.
"""

import re
from urllib.parse import urlsplit

from samovar_agent.adapters.urllib_http import check_url
from samovar_agent.domain.errors import ConfigurationError
from samovar_agent.domain.session import DataSession, S3Access
from samovar_agent.settings import PREFIX, S3Key

MAPPING_KEY = "mapping/samovar.duckdb"
EXTENSIONS = ("httpfs", "avro", "iceberg")
BUCKET = re.compile(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]")  # S3 bucket naming rules
URL_STYLES = ("vhost", "path")  # DuckDB URL_STYLE: cloud.ru addresses buckets by host, a local MinIO by path
NO_KEY = (
    "No S3 key: an admin creates a read-only S3 key in the Samovar Data cabinet (S3 keys); enter its Access Key ID, "
    "Secret Access Key and bucket in the plugin settings."
)


def endpoint_url(endpoint: str) -> str:
    """The cabinet shows the endpoint as a URL; a bare host means HTTPS."""
    return endpoint if "://" in endpoint else "https://" + endpoint


class S3KeySessionProvider:
    def __init__(self, key: S3Key | None) -> None:
        self._key = key

    @property
    def mode(self) -> str:
        return "platform"

    def problem(self) -> str | None:
        """Why the key cannot be used, or None."""
        key = self._key
        if key is None:
            return NO_KEY
        if not (key.key_id and key.secret and key.bucket):
            return "The S3 key needs all of the Access Key ID, the Secret Access Key and the bucket from the cabinet."
        if not BUCKET.fullmatch(key.bucket):
            return "The bucket is a bucket name from the cabinet, like samovar-t-1a2b3c (no s3://)."
        if key.url_style not in URL_STYLES:
            return f"{PREFIX}S3_URL_STYLE must be one of {list(URL_STYLES)}."
        try:
            check_url(endpoint_url(key.endpoint))  # the S3 traffic is HTTPS, plain HTTP only to a loopback host
        except ConfigurationError as error:
            return f"S3 endpoint: {error}"
        return None

    def open(self) -> DataSession:
        problem = self.problem()
        if problem is not None or self._key is None:
            raise ConfigurationError(problem or NO_KEY)
        key = self._key
        endpoint = urlsplit(endpoint_url(key.endpoint))
        bucket = f"s3://{key.bucket}/"
        return DataSession(
            mapping_location=bucket + MAPPING_KEY,
            allowed_directories=(bucket,),
            extensions=EXTENSIONS,
            s3=S3Access(
                key_id=key.key_id,
                secret=key.secret,
                endpoint=endpoint.netloc,
                region=key.region,
                url_style=key.url_style,
                use_ssl=endpoint.scheme == "https",
                scope=bucket,
            ),
        )
