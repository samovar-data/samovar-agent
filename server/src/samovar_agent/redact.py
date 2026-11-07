"""Removes secrets from anything the agent shows or logs: the S3 key and presigned URLs."""

import logging
import re
from collections.abc import Callable, Iterable

MASK = "[redacted]"
PATTERNS = (
    re.compile(r"\bhttps?://\S*[?&]X-Amz-\S*", re.IGNORECASE),
    re.compile(r"X-Amz-[A-Za-z-]+=[^&\s'\"]*", re.IGNORECASE),
    re.compile(r"(?i)\b(session_token|secret_access_key|access_key_id|authorization)(\W{1,4})[^\s,'\"}]+"),
)


class Redactor:
    def __init__(self, secrets: Callable[[], Iterable[str]]) -> None:
        self._secrets = secrets

    def redact(self, text: str) -> str:
        for secret in sorted((s for s in self._secrets() if len(s) >= 4), key=len, reverse=True):
            text = text.replace(secret, MASK)
        for pattern in PATTERNS:
            text = pattern.sub(_mask, text)
        return text


def _mask(match: re.Match[str]) -> str:
    if match.lastindex and match.lastindex >= 2:
        return f"{match.group(1)}{match.group(2)}{MASK}"
    return MASK


class RedactingFilter(logging.Filter):
    def __init__(self, redactor: Redactor) -> None:
        super().__init__()
        self._redactor = redactor

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._redactor.redact(record.getMessage())
        record.args = None
        if record.exc_info:
            record.exc_text = self._redactor.redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        return True
