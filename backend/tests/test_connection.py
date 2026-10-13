from unittest.mock import Mock

import pytest

from data_chat.core.config import Settings
from data_chat.data import connection
from data_chat.data.connection import (
    SQLServerConfigurationError,
    create_sql_server_engine,
)


def test_engine_factory_requires_nonempty_connection_string() -> None:
    with pytest.raises(SQLServerConfigurationError):
        create_sql_server_engine(Settings.model_validate({}))

    with pytest.raises(SQLServerConfigurationError):
        create_sql_server_engine(
            Settings.model_validate({"sql_server_odbc_connection_string": "   "})
        )


@pytest.mark.parametrize(
    "connection_string",
    [
        "Driver={ODBC Driver 18 for SQL Server};Server=localhost;",
        (
            "Driver={ODBC Driver 18 for SQL Server};Server=localhost;"
            "Encrypt=no;TrustServerCertificate=no;"
        ),
        (
            "Driver={ODBC Driver 18 for SQL Server};Server=localhost;"
            "Encrypt=yes;"
        ),
        (
            "Driver={ODBC Driver 18 for SQL Server};Server=localhost;"
            "TrustServerCertificate=no;"
        ),
    ],
)
def test_engine_factory_rejects_nonsecure_or_ambiguous_tls_options(
    monkeypatch: pytest.MonkeyPatch,
    connection_string: str,
) -> None:
    create_engine = Mock()
    monkeypatch.setattr(connection, "create_engine", create_engine)
    settings = Settings.model_validate(
        {"sql_server_odbc_connection_string": connection_string}
    )

    with pytest.raises(SQLServerConfigurationError):
        create_sql_server_engine(settings)

    create_engine.assert_not_called()


def test_engine_factory_configures_lazy_sql_server_engine_without_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = Mock()
    create_engine = Mock(return_value=engine)
    listen = Mock()
    monkeypatch.setattr(connection, "create_engine", create_engine)
    monkeypatch.setattr(connection.event, "listen", listen)
    settings = Settings.model_validate(
        {
            "sql_server_odbc_connection_string": (
                "Driver={ODBC Driver 18 for SQL Server};"
                "Server=localhost;Database=WorldCup;"
                "Trusted_Connection=yes;Encrypt=yes;"
                "TrustServerCertificate=no;"
            ),
            "sql_server_connection_timeout_seconds": 7,
            "sql_server_query_timeout_seconds": 19,
        }
    )

    result = create_sql_server_engine(settings)

    assert result is engine
    create_engine.assert_called_once()
    url, = create_engine.call_args.args
    assert url.drivername == "mssql+pyodbc"
    assert url.query["odbc_connect"].startswith("Driver=")
    assert create_engine.call_args.kwargs["pool_pre_ping"] is True
    assert create_engine.call_args.kwargs["connect_args"] == {"timeout": 7}
    listen.assert_called_once()
    assert listen.call_args.args[:2] == (engine, "connect")
    engine.connect.assert_not_called()


def test_engine_factory_allows_trusting_certificate_only_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = Mock()
    create_engine = Mock(return_value=engine)
    listen = Mock()
    monkeypatch.setattr(connection, "create_engine", create_engine)
    monkeypatch.setattr(connection.event, "listen", listen)
    settings = Settings.model_validate(
        {
            "app_environment": "development",
            "sql_server_odbc_connection_string": (
                "Driver={ODBC Driver 17 for SQL Server};"
                "Server=DESKTOP-EN1QC5A;Database=WorldCup2026Dev;"
                "Trusted_Connection=yes;Encrypt=yes;"
                "TrustServerCertificate=yes;"
            ),
        }
    )

    assert create_sql_server_engine(settings) is engine


@pytest.mark.parametrize("environment", ["test", "production"])
def test_engine_factory_rejects_trusting_certificate_outside_development(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
) -> None:
    create_engine = Mock()
    monkeypatch.setattr(connection, "create_engine", create_engine)
    settings = Settings.model_validate(
        {
            "app_environment": environment,
            "sql_server_odbc_connection_string": (
                "Driver={ODBC Driver 17 for SQL Server};"
                "Server=DESKTOP-EN1QC5A;Database=WorldCup2026Dev;"
                "Trusted_Connection=yes;Encrypt=yes;"
                "TrustServerCertificate=yes;"
            ),
        }
    )

    with pytest.raises(
        SQLServerConfigurationError,
        match="only in development",
    ):
        create_sql_server_engine(settings)

    create_engine.assert_not_called()


def test_connection_hook_sets_bounded_query_timeout() -> None:
    dbapi_connection = Mock()
    dbapi_connection.timeout = 0
    set_timeout = connection._connection_timeout_handler(23)

    set_timeout(dbapi_connection, Mock())

    assert dbapi_connection.timeout == 23
