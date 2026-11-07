"""Conversion of DuckDB result values into JSON-compatible values (tool output, JSON export, charts)."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


def json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return str(value)
    if isinstance(value, (UUID, bytes)):
        return value.hex if isinstance(value, UUID) else value.hex()
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    return str(value)
