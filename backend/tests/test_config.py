import pytest
from pydantic import ValidationError

from data_chat.core.config import Settings


def test_settings_accept_supported_values() -> None:
    settings = Settings.model_validate(
        {"app_environment": "test", "log_level": "DEBUG"}
    )

    assert settings.app_environment == "test"
    assert settings.log_level == "DEBUG"


def test_settings_reject_invalid_log_level() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"log_level": "TRACE"})


def test_openai_request_timeout_is_bounded() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"openai_request_timeout_seconds": 0})

    with pytest.raises(ValidationError):
        Settings.model_validate({"openai_request_timeout_seconds": 121})


def test_sql_server_timeouts_are_bounded() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"sql_server_query_timeout_seconds": 0})

    with pytest.raises(ValidationError):
        Settings.model_validate({"sql_server_connection_timeout_seconds": 121})
