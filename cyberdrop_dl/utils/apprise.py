from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING

import apprise
import rich
from pydantic import ValidationError
from rich.text import Text

from cyberdrop_dl.config_definitions.custom_types import AppriseURLModel
from cyberdrop_dl.utils import constants
from cyberdrop_dl.utils.logger import log, log_debug, log_spacer
from cyberdrop_dl.utils.yaml import handle_validation_error

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager

DEFAULT_APPRISE_MESSAGE = {
    "body": "Finished downloading. Enjoy :)",
    "title": "Cyberdrop-DL",
    "body_format": apprise.NotifyFormat.TEXT,
}


@dataclass
class AppriseURL:
    url: str
    tags: set[str]
    raw_url: str


OS_URLS = ["windows://", "macosx://", "dbus://", "qt://", "glib://", "kde://"]


class LogLevel(IntEnum):
    NOTSET: 0
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


LOG_LEVEL_NAMES = [x.name for x in LogLevel]


@dataclass
class LogLine:
    level: LogLevel = LogLevel.INFO
    msg: str = ""


def get_apprise_urls(manager: Manager) -> list[AppriseURL] | None:
    apprise_file = manager.path_manager.config_folder / manager.config_manager.loaded_config / "apprise.txt"
    apprise_fixed = manager.cache_manager.get("apprise_fixed")
    if not apprise_fixed:
        if os.name == "nt":
            with apprise_file.open("a") as f:
                f.write("windows://\n")
        manager.cache_manager.save("apprise_fixed", True)

    if not apprise_file.is_file():
        return

    try:
        with apprise_file.open(encoding="utf8") as file:
            urls = {line.strip() for line in file}
            return simplify_urls([AppriseURLModel(url=url) for url in urls])

    except ValidationError as e:
        sources = {"AppriseURL": apprise_file}
        handle_validation_error(e, sources=sources)
        return


def simplify_urls(apprise_urls: list[AppriseURLModel]) -> list[AppriseURL]:
    final_urls = []

    def use_simplified(url: str) -> bool:
        special_urls = OS_URLS
        return any(key in url.casefold() for key in special_urls)

    for apprise_url in apprise_urls:
        url = str(apprise_url.url.get_secret_value())
        tags = apprise_url.tags or {"no_logs"}
        if use_simplified(url):
            tags = {"simplified"}
        new_model = apprise_url.model_copy(update={"tags": tags})
        raw_url = new_model.model_dump()
        entry = AppriseURL(url=url, tags=tags, raw_url=raw_url)
        final_urls.append(entry)
    return sorted(final_urls, key=lambda x: x.url)


def process_results(all_urls: list[str], results_dict: dict[str, bool | None], apprise_logs: str) -> None:
    results = [r for r in results_dict.values() if r is not None]
    for key, value in results_dict.items():
        if value:
            results_dict[key] = str(constants.NotificationResultText.SUCCESS.value)
        elif value is None:
            results_dict[key] = str(constants.NotificationResultText.NONE.value)
        else:
            results_dict[key] = str(constants.NotificationResultText.FAILED.value)

    if not results:
        final_result = constants.NotificationResultText.NONE.value
    if all(results):
        final_result = constants.NotificationResultText.SUCCESS.value
    elif any(results):
        final_result = constants.NotificationResultText.PARTIAL.value
    else:
        final_result = constants.NotificationResultText.FAILED.value

    log_spacer(10, log_to_console=False)
    rich.print("Apprise notifications results:", final_result)
    logger = log_debug if all(results) else log
    logger(f"Apprise notifications results: {final_result}")
    logger(f"PARSED_APPRISE_URLs: \n{json.dumps(all_urls, indent=4)}\n")
    logger(f"RESULTS_BY_TAGS: \n{json.dumps(results_dict, indent=4)}")
    log_spacer(10, log_to_console=False)
    parsed_log_lines = parse_apprise_logs(apprise_logs)
    for line in parsed_log_lines:
        logger(level=line.level.value, message=line.msg)


def reduce_logs(apprise_logs: str) -> list[str]:
    lines = apprise_logs.splitlines()
    to_exclude = ["Running Post-Download Processes For Config"]
    return [line for line in lines if all(word not in line for word in to_exclude)]


def parse_apprise_logs(apprise_logs: str) -> list[LogLine]:
    lines = reduce_logs(apprise_logs)
    current_line: LogLine = LogLine()
    parsed_lines: list[LogLine] = []
    for line in lines:
        log_level = line[0:8].strip()
        if log_level and log_level not in LOG_LEVEL_NAMES:
            current_line.msg += f"\n{line}"
            continue

        if current_line.msg != "":
            parsed_lines.append(current_line)
        current_line = LogLine(LogLevel[log_level], line[10::])
    return parsed_lines


def process_file(original_file_path: Path):
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        temp_file = temp_dir_path / original_file_path.resolve().name
        shutil.copy(original_file_path, temp_file)


async def send_apprise_notifications(manager: Manager) -> None:
    apprise_urls = get_apprise_urls(manager)
    if not apprise_urls:
        return

    rich.print("\nSending Apprise Notifications.. ")
    text: Text = constants.LOG_OUTPUT_TEXT
    constants.LOG_OUTPUT_TEXT = Text("")

    apprise_obj = apprise.Apprise()
    for apprise_url in apprise_urls:
        apprise_obj.add(apprise_url.url, tag=apprise_url.tags)

    main_log = manager.path_manager.main_log.resolve()
    notifications_to_send = {
        "no_logs": {"body": text.plain},
        "attach_logs": {"body": text.plain, "attach": main_log},
        "simplified": {},
    }

    results = {}
    all_urls = [x.raw_url for x in apprise_urls]

    with (
        apprise.LogCapture(level=10, fmt="%(levelname)-7s - %(message)s") as capture,
        tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir,
    ):
        temp_dir = Path(temp_dir)
        temp_main_log = temp_dir / main_log.name
        shutil.copy(main_log, temp_main_log)

        notifications_to_send = {
            "no_logs": {"body": text.plain},
            "attach_logs": {"body": text.plain, "attach": str(temp_main_log.resolve())},
            "simplified": {},
        }
        for tag, extras in notifications_to_send.items():
            msg = DEFAULT_APPRISE_MESSAGE | extras
            results[tag] = await apprise_obj.async_notify(**msg, tag=tag)
        apprise_logs = capture.getvalue()

    process_results(all_urls, results, apprise_logs)
