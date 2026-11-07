"""Read access to the tenant's data, as the engine needs it."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class S3Access:
    key_id: str = field(repr=False)
    secret: str = field(repr=False)
    endpoint: str
    region: str
    url_style: str
    use_ssl: bool
    scope: str


@dataclass(frozen=True)
class DataSession:
    mapping_location: str
    allowed_directories: tuple[str, ...]
    extensions: tuple[str, ...]
    s3: S3Access | None

    def secrets(self) -> tuple[str, ...]:
        """Values that must never appear in tool output or logs."""
        if self.s3 is None:
            return ()
        return (self.s3.key_id, self.s3.secret)
