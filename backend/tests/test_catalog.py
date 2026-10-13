from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from sqlalchemy import Connection
from sqlalchemy.dialects import mssql

from data_chat.data.catalog import (
    AUTHORIZED_QUERIES,
    UnsupportedQueryError,
    execute_authorized_query,
)


def test_unknown_query_is_rejected_before_database_access() -> None:
    connection = Mock(spec=Connection)

    with pytest.raises(UnsupportedQueryError):
        execute_authorized_query(
            connection,
            "arbitrary_sql",
            {},
            max_rows=100,
        )

    connection.execute.assert_not_called()


def test_catalog_rejects_unexpected_parameters() -> None:
    connection = Mock(spec=Connection)

    with pytest.raises(ValidationError):
        execute_authorized_query(
            connection,
            "matches_for_team",
            {"team_name": "Example", "sql": "DELETE FROM wc2026.Team"},
            max_rows=100,
        )

    connection.execute.assert_not_called()


def test_user_text_is_bound_as_a_value_not_sql() -> None:
    connection = Mock(spec=Connection)
    connection.execute.return_value.mappings.return_value.all.return_value = []
    user_value = "Team' OR 1=1 --"

    rows = execute_authorized_query(
        connection,
        "matches_for_team",
        {"team_name": user_value},
        max_rows=100,
    )

    statement, parameters = connection.execute.call_args.args
    assert rows == []
    assert user_value not in str(statement)
    assert parameters == {"team_name": user_value, "result_limit": 100}


def test_each_registered_query_is_static_and_has_a_result_limit() -> None:
    assert AUTHORIZED_QUERIES

    for query in AUTHORIZED_QUERIES.values():
        assert ":result_limit" in str(query.statement)
        compiled = query.statement.compile(dialect=mssql.dialect(paramstyle="qmark"))
        expected_parameters = set(query.parameters.model_fields) | {"result_limit"}
        assert set(compiled.params) == expected_parameters


@pytest.mark.parametrize("max_rows", [0, 1001])
def test_invalid_result_limit_is_rejected_before_database_access(
    max_rows: int,
) -> None:
    connection = Mock(spec=Connection)

    with pytest.raises(ValueError, match="max_rows must be between"):
        execute_authorized_query(
            connection,
            "venues",
            {},
            max_rows=max_rows,
        )

    connection.execute.assert_not_called()
