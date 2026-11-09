"""SQL templates, loaded once from a package's `sql/*.sql` files into an immutable object (field `a_b` <- `a-b.sql`)."""

from dataclasses import dataclass, fields, is_dataclass
from importlib import resources
from typing import Any, TypeVar

T = TypeVar("T")


def load_sql_files(cls: type[T], package: str) -> T:
    if not is_dataclass(cls):
        raise TypeError(f"{cls.__name__} must be a dataclass")
    folder = resources.files(package).joinpath("sql")
    texts: dict[str, Any] = {
        field.name: folder.joinpath(field.name.replace("_", "-") + ".sql").read_text(encoding="utf-8")
        for field in fields(cls)
    }
    return cls(**texts)


@dataclass(frozen=True)
class Queries:
    attach: str
    attached: str
    load_extension: str
    lock: str
    object_size: str
    platform: str
    resolved: str
    s3_defaults: str
    s3_endpoint: str
    secret: str
    serialize: str
    set_demo_shift: str
    text_timestamps: str
    use: str
    views: str
    wrap_query: str

    @classmethod
    def load(cls) -> "Queries":
        return load_sql_files(cls, "samovar_agent")
