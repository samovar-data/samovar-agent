import pytest

from samovar_agent.engine.sql_template import (
    Boolean,
    Identifier,
    Integer,
    Literal,
    LiteralList,
    LiteralStruct,
    SqlTemplateError,
    render,
)


def test_literal_doubles_single_quotes_so_values_cannot_close_the_string() -> None:
    assert render("{{v}}", {"v": Literal("a'); DROP")}) == "'a''); DROP'"


def test_identifier_accepts_only_plain_lowercase_names() -> None:
    assert render("{{n}}", {"n": Identifier("httpfs")}) == "httpfs"
    with pytest.raises(SqlTemplateError):
        render("{{n}}", {"n": Identifier("httpfs; select")})


def test_missing_placeholder_value_is_an_error_not_an_empty_string() -> None:
    with pytest.raises(SqlTemplateError):
        render("{{a}} {{b}}", {"a": Integer(1)})


def test_lists_structs_and_booleans_render_as_duckdb_literals() -> None:
    assert render("{{l}}", {"l": LiteralList(("s3://b/dds/", "x'y"))}) == "['s3://b/dds/', 'x''y']"
    assert render("{{s}}", {"s": LiteralStruct((("a", "VARCHAR"),))}) == "{'a': 'VARCHAR'}"
    assert render("{{b}}", {"b": Boolean(False)}) == "false"
