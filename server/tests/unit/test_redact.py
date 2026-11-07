import logging
import sys

from samovar_agent.redact import MASK, RedactingFilter, Redactor


def redactor(*secrets: str) -> Redactor:
    return Redactor(lambda: secrets)


def test_known_secret_values_are_masked() -> None:
    assert redactor("sts-secret-123").redact("failed with sts-secret-123 here") == f"failed with {MASK} here"


def test_presigned_urls_and_amz_parameters_are_masked() -> None:
    text = "GET https://s3.example/b/mapping.duckdb?X-Amz-Credential=AK%2F1&X-Amz-Signature=abc failed"
    out = redactor().redact(text)
    assert "X-Amz-" not in out and "abc" not in out


def test_credential_fields_are_masked_even_when_the_value_is_unknown() -> None:
    out = redactor().redact('secret_access_key="sec123" session_token="tok123" Authorization: Bearer x')
    assert "sec123" not in out and "tok123" not in out


def test_log_records_and_tracebacks_are_redacted() -> None:
    record = logging.LogRecord("x", logging.ERROR, __file__, 1, "key %s", ("sts-secret-123",), None)
    try:
        raise RuntimeError("boom sts-secret-123")
    except RuntimeError:
        record.exc_info = sys.exc_info()
    RedactingFilter(redactor("sts-secret-123")).filter(record)
    assert "sts-secret-123" not in record.getMessage()
    assert record.exc_text is not None and "sts-secret-123" not in record.exc_text
