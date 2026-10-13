from collections.abc import Mapping

from sqlalchemy import Engine
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from data_chat.data.catalog import execute_authorized_query
from data_chat.data.connection import dispose_engine
from data_chat.services.chat import (
    DataAccessError,
    QueryTimeoutError,
)


class CatalogRepository:
    def __init__(self, engine: Engine, *, max_rows: int) -> None:
        if max_rows < 1:
            raise ValueError("max_rows must be greater than zero.")
        self._engine = engine
        self._max_rows = max_rows

    def close(self) -> None:
        dispose_engine(self._engine)

    def execute(
        self,
        query_id: str,
        parameters: Mapping[str, object],
        *,
        max_rows: int,
    ) -> list[dict[str, object]]:
        if not 1 <= max_rows:
            raise ValueError("max_rows must be greater than zero.")
        effective_limit = min(max_rows, self._max_rows)
        try:
            with self._engine.connect() as connection:
                return execute_authorized_query(
                    connection,
                    query_id,
                    parameters,
                    max_rows=effective_limit,
                )
        except DBAPIError as exc:
            if _is_odbc_timeout(exc):
                raise QueryTimeoutError(
                    "The SQL Server query exceeded its configured timeout."
                ) from exc
            raise DataAccessError(
                "The SQL Server query could not be completed."
            ) from exc
        except SQLAlchemyError as exc:
            raise DataAccessError(
                "The SQL Server data service is unavailable."
            ) from exc


def _is_odbc_timeout(error: DBAPIError) -> bool:
    original_args = getattr(error.orig, "args", ())
    return any(
        isinstance(argument, str)
        and argument.upper().startswith(("HYT00", "HYT01"))
        for argument in original_args
    )
