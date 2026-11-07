"""A synthetic client S3 key (no real credentials)."""

from samovar_agent.settings import S3Key

KEY_ID = "S3KEYID0123456789TEST"
SECRET = "s3-secret-0123456789abcdefSECRET"
BUCKET = "samovar-t-demo"


def s3_key(endpoint: str = "https://s3.cloud.ru") -> S3Key:
    return S3Key(key_id=KEY_ID, secret=SECRET, bucket=BUCKET, endpoint=endpoint)
