from unittest.mock import MagicMock, Mock

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import DBAPIError

from data_chat.data import repository
from data_chat.data.catalog import MAX_QUERY_RESULT_ROWS
from data_chat.data.repository import CatalogRepository
from data_chat.services.chat import DataAccessError, QueryTimeoutError


def test_repository_passes_only_catalog_query_and_bounded_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = Mock()
    engine = Mock(spec=Engine)
    connection_context = MagicMock()
    connection_context.__enter__.return_value = connection
    engine.connect.return_value = connection_context
    query_executor = Mock(return_value=[{"team_name": "Example"}])
    monkeypatch.setattr(repository, "execute_authorized_query", query_executor)
    data_repository = CatalogRepository(engine, max_rows=25)

    rows = data_repository.execute(
        "tournament_teams",
        {},
        max_rows=MAX_QUERY_RESULT_ROWS,
    )

    assert rows == [{"team_name": "Example"}]
    query_executor.assert_called_once_with(
        connection,
        "tournament_teams",
        {},
        max_rows=25,
    )
    engine.connect.assert_called_once_with()


def test_repository_preserves_catalog_validation_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = Mock(spec=Engine)
    connection_context = MagicMock()
    engine.connect.return_value = connection_context
    query_executor = Mock(side_effect=ValueError("invalid query parameters"))
    monkeypatch.setattr(repository, "execute_authorized_query", query_executor)
    data_repository = CatalogRepository(engine, max_rows=100)

    with pytest.raises(ValueError, match="invalid query parameters"):
        data_repository.execute("tournament_teams", {}, max_rows=10)


def test_repository_maps_odbc_query_timeout() -> None:
    engine = Mock(spec=Engine)
    connection = Mock()
    connection_context = MagicMock()
    connection_context.__enter__.return_value = connection
    engine.connect.return_value = connection_context
    original = RuntimeError("HYT00 query timeout")
    error = DBAPIError("SELECT ...", {}, original)
    connection.execute.side_effect = error
    data_repository = CatalogRepository(engine, max_rows=100)

    with pytest.raises(QueryTimeoutError) as exc_info:
        data_repository.execute(
            "venues",
            {},
            max_rows=10,
        )

    assert "HYT00" not in str(exc_info.value)


def test_repository_maps_other_dbapi_failures_safely() -> None:
    engine = Mock(spec=Engine)
    connection = Mock()
    connection_context = MagicMock()
    connection_context.__enter__.return_value = connection
    engine.connect.return_value = connection_context
    error = DBAPIError("SELECT ...", {}, RuntimeError("credentials leaked"))
    connection.execute.side_effect = error
    data_repository = CatalogRepository(engine, max_rows=100)

    with pytest.raises(DataAccessError) as exc_info:
        data_repository.execute("venues", {}, max_rows=10)

    assert "credentials leaked" not in str(exc_info.value)


def test_repository_validates_configured_row_limit() -> None:
    with pytest.raises(ValueError, match="max_rows"):
        CatalogRepository(Mock(spec=Engine), max_rows=0)


def test_sql_server_timeout_uses_documented_odbc_sqlstates() -> None:
    assert repository._is_odbc_timeout(
        DBAPIError("SELECT ...", {}, RuntimeError("HYT00 timeout"))
    )
    assert repository._is_odbc_timeout(
        DBAPIError("SELECT ...", {}, RuntimeError("HYT01 timeout"))
    )
    assert not repository._is_odbc_timeout(
        DBAPIError("SELECT ...", {}, RuntimeError("08001 connection failure"))
    )
