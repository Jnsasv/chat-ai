from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL

from data_chat.core.config import Settings


class SQLServerConfigurationError(RuntimeError):
    pass


def dispose_engine(engine: Engine) -> None:
    engine.dispose()


def create_sql_server_engine(settings: Settings) -> Engine:
    if settings.sql_server_odbc_connection_string is None:
        raise SQLServerConfigurationError(
            "SQL Server connection settings are not configured."
        )
    connection_string = (
        settings.sql_server_odbc_connection_string.get_secret_value().strip()
    )
    if not connection_string:
        raise SQLServerConfigurationError(
            "SQL Server connection settings are not configured."
        )
    connection_options = _odbc_options(connection_string)
    if connection_options.get("encrypt", "").casefold() not in {
        "yes",
        "true",
        "mandatory",
        "strict",
    }:
        raise SQLServerConfigurationError(
            "SQL Server connections must explicitly enable encryption."
        )
    trust_server_certificate = connection_options.get(
        "trustservercertificate", ""
    ).casefold()
    if trust_server_certificate in {"yes", "true"}:
        if settings.app_environment != "development":
            raise SQLServerConfigurationError(
                "Trusting the SQL Server certificate is allowed only in development."
            )
    elif trust_server_certificate not in {"no", "false"}:
        raise SQLServerConfigurationError(
            "SQL Server certificate validation must remain enabled."
        )

    engine = create_engine(
        URL.create(
            "mssql+pyodbc",
            query={"odbc_connect": connection_string},
        ),
        pool_pre_ping=True,
        connect_args={
            "timeout": settings.sql_server_connection_timeout_seconds,
        },
    )
    event.listen(
        engine,
        "connect",
        _connection_timeout_handler(settings.sql_server_query_timeout_seconds),
    )
    return engine


def _connection_timeout_handler(timeout_seconds: int):
    def set_timeout(connection: object, connection_record: object) -> None:
        del connection_record
        setattr(connection, "timeout", timeout_seconds)

    return set_timeout


def _odbc_options(connection_string: str) -> dict[str, str]:
    options: dict[str, str] = {}
    for item in connection_string.split(";"):
        key, separator, value = item.partition("=")
        if separator:
            options[key.strip().casefold()] = value.strip().strip("{}").strip()
    return options
