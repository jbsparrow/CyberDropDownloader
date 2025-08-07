from __future__ import annotations

from dataclasses import Field
from typing import TYPE_CHECKING, Any, TypeVar

import pytest

from cyberdrop_dl.managers.manager import Manager, merge_dicts

if TYPE_CHECKING:
    from pydantic import BaseModel

    M = TypeVar("M", bound=BaseModel)


def update_model(model: M, **kwargs: Any) -> M:
    return model.model_validate(model.model_dump() | kwargs)


class TestMergeDicts:
    def test_overwrite(self) -> None:
        dict1 = {"a": 1, "b": 2}
        dict2 = {"b": 3, "c": 4}
        expected = {"a": 1, "b": 3, "c": 4}
        assert merge_dicts(dict1, dict2) == expected

    def test_merge_with_new_keys(self) -> None:
        dict1 = {"a": 1}
        dict2 = {"b": 2, "c": 3}
        expected = {"a": 1, "b": 2, "c": 3}
        assert merge_dicts(dict1, dict2) == expected

    def test_merge_recursive(self) -> None:
        dict1 = {
            "a": {
                "b": 1,
                "c": 2,
            },
            "d": 3,
        }
        dict2 = {
            "a": {
                "b": 4,
                "e": 4,
                "f": {
                    "g": 5,
                    "h": 6,
                },
            },
            "i": 7,
        }
        expected = {
            "a": {
                "b": 4,
                "c": 2,
                "e": 4,
                "f": {
                    "g": 5,
                    "h": 6,
                },
            },
            "d": 3,
            "i": 7,
        }
        assert merge_dicts(dict1, dict2) == expected

    def test_merge_with_empty_dict1(self) -> None:
        dict1 = {}
        dict2 = {"a": 1, "b": 2}
        expected = {"a": 1, "b": 2}
        assert merge_dicts(dict1, dict2) == expected

    def test_merge_with_empty_dict2(self) -> None:
        dict1 = {"a": 1, "b": 2}
        dict2 = {}
        expected = {"a": 1, "b": 2}
        assert merge_dicts(dict1, dict2) == expected

    def test_merge_with_both_empty_dicts(self) -> None:
        dict1 = {}
        dict2 = {}
        expected = {}
        assert merge_dicts(dict1, dict2) == expected

    def test_dict_overwrites_value(self) -> None:
        dict1 = {"a": 1}
        dict2 = {"a": {"x": 1}}
        expected = {"a": {"x": 1}}
        assert merge_dicts(dict1, dict2) == expected

    def test_value_should_not_overwrite_dict(self) -> None:
        dict1 = {"a": {"x": 1}}
        dict2 = {"a": 1}
        expected = {"a": {"x": 1}}
        assert merge_dicts(dict1, dict2) == expected


@pytest.mark.parametrize(
    "webhook, output",
    [
        ("https://example.com", "**********"),
        ("attach_logs=https://example.com", "attach_logs=**********"),
    ],
)
def test_args_logging_should_censor_webhook(
    running_manager: Manager, logs: pytest.LogCaptureFixture, webhook: str, output: str
) -> None:
    logs_model = running_manager.config_manager.settings_data.logs
    running_manager.config_manager.settings_data.logs = update_model(logs_model, webhook=webhook)
    running_manager.args_logging()
    assert logs.messages
    assert "Starting Cyberdrop-DL Process" in logs.text
    assert webhook not in logs.text
    webhook_line = next(msg for msg in logs.text.splitlines() if '"webhook"' in msg)
    _, _, webhook_text = webhook_line.partition(":")
    webhook_url = webhook_text.strip().split(" ")[0].replace('"', "").strip()
    assert output == webhook_url


async def test_async_db_close(running_manager: Manager) -> None:
    await running_manager.async_startup()
    assert not isinstance(running_manager.db_manager, Field)
    assert not isinstance(running_manager.hash_manager, Field)
    assert "overwrite" not in str(running_manager.log_manager.main_log)
    await running_manager.async_db_close()
    assert isinstance(running_manager.db_manager, Field)
    assert isinstance(running_manager.hash_manager, Field)
    await running_manager.close()
