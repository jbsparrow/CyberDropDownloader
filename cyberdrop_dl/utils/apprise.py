from __future__ import annotations

import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from enum import IntEnum
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING

import apprise
import rich
from pydantic import ValidationError
from rich.text import Text

from cyberdrop_dl import constants
from cyberdrop_dl.models import AppriseURLModel
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

    @property
    def raw_url(self):
        tags = sorted(self.tags)
        return f"{','.join(tags)}{'=' if tags else ''}{self.url}"


OS_URLS = ["windows://", "macosx://", "dbus://", "qt://", "glib://", "kde://"]


class LogLevel(IntEnum):
    NOTSET = 0
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


def get_apprise_urls(*, file: Path | None = None, urls: list[str] | None = None) -> list[AppriseURL]:
    """
    Get Apprise URLs from the specified file or directly from a provided URL.

    Args:
        file (Path, optional): The path to the file containing Apprise URLs.
        url (str, optional): A single Apprise URL to be processed.

    Returns:
        list[AppriseURL] | None: A list of processed Apprise URLs, or None if no valid URLs are found.
    """
    if not (urls or file):
        raise ValueError("Neither url of file were supplied")
    if urls and file:
        raise ValueError("url of file are mutually exclusive")

    if file:
        if not file.is_file():
            return []
        with file.open(encoding="utf8") as apprise_file:
            urls = [line.strip() for line in apprise_file if line.strip()]

    if not urls:
        return []
    try:
        return _simplify_urls([AppriseURLModel.model_validate({"url": url}) for url in set(urls)])
        AppriseURLModel.model_construct()

    except ValidationError as e:
        handle_validation_error(e, title="Apprise", file=file)
        sys.exit(1)


def _simplify_urls(apprise_urls: list[AppriseURLModel]) -> list[AppriseURL]:
    final_urls = []
    valid_tags = {"no_logs", "attach_logs", "simplified"}

    def use_simplified(url: str) -> bool:
        special_urls = OS_URLS
        return any(key in url.casefold() for key in special_urls)

    for apprise_url in apprise_urls:
        url = str(apprise_url.url.get_secret_value())
        tags = apprise_url.tags or {"no_logs"}
        if not any(tag in tags for tag in valid_tags):
            tags = tags | {"no_logs"}
        if use_simplified(url):
            tags = tags - valid_tags | {"simplified"}
        entry = AppriseURL(url=url, tags=tags)
        final_urls.append(entry)
    return sorted(final_urls, key=lambda x: x.url)


def _process_results(
    all_urls: list[str], results: dict[str, bool | None], apprise_logs: str
) -> tuple[constants.NotificationResult, list[LogLine]]:
    result = [r for r in results.values() if r is not None]
    result_dict = {}
    for key, value in results.items():
        if value:
            result_dict[key] = str(constants.NotificationResult.SUCCESS.value)
        elif value is None:
            result_dict[key] = str(constants.NotificationResult.NONE.value)
        else:
            result_dict[key] = str(constants.NotificationResult.FAILED.value)

    if all(result):
        final_result = constants.NotificationResult.SUCCESS
    elif any(result):
        final_result = constants.NotificationResult.PARTIAL
    else:
        final_result = constants.NotificationResult.FAILED

    log_spacer(10, log_to_console=False, log_to_file=not all(result))
    rich.print("Apprise notifications results:", final_result.value)
    logger = log_debug if all(result) else log
    logger(f"Apprise notifications results: {final_result.value}")
    logger(f"PARSED_APPRISE_URLs: \n{json.dumps(all_urls, indent=4)}\n")
    logger(f"RESULTS_BY_TAGS: \n{json.dumps(result_dict, indent=4)}")
    log_spacer(10, log_to_console=False, log_to_file=not all(result))
    parsed_log_lines = _parse_apprise_logs(apprise_logs)
    for line in parsed_log_lines:
        logger(level=line.level.value, message=line.msg)
    return final_result, parsed_log_lines


def _reduce_logs(apprise_logs: str) -> list[str]:
    lines = apprise_logs.splitlines()
    to_exclude = ["Running Post-Download Processes For Config"]
    return [line for line in lines if all(word not in line for word in to_exclude)]


def _parse_apprise_logs(apprise_logs: str) -> list[LogLine]:
    lines = _reduce_logs(apprise_logs)
    current_line: LogLine = LogLine()
    parsed_lines: list[LogLine] = []
    for line in lines:
        log_level = line[0:8].strip()
        if log_level and log_level not in LOG_LEVEL_NAMES:  # pragma: no cover
            current_line.msg += f"\n{line}"
            continue

        if current_line.msg != "":
            parsed_lines.append(current_line)
        current_line = LogLine(LogLevel[log_level], line[10::])
    if lines:
        parsed_lines.append(current_line)
    return parsed_lines


async def send_apprise_notifications(manager: Manager) -> tuple[constants.NotificationResult, list[LogLine]]:
    """
    Send notifications using Apprise based on the URLs set in the manager.

    Args:
        manager (Manager): The manager instance containing.

    Returns:
        tuple[NotificationResult, list[LogLine]]: A tuple containing the overall notification result and a list of log lines.

    """
    apprise_urls = manager.config_manager.apprise_urls
    if not apprise_urls:
        return constants.NotificationResult.NONE, [LogLine(msg=constants.NotificationResult.NONE.value.plain)]

    rich.print("\nSending Apprise Notifications.. ")
    text: Text = constants.LOG_OUTPUT_TEXT
    constants.LOG_OUTPUT_TEXT = Text("")

    apprise_obj = apprise.Apprise()
    for apprise_url in apprise_urls:
        apprise_obj.add(apprise_url.url, tag=apprise_url.tags)

    main_log = manager.path_manager.main_log
    results = {}
    all_urls = [x.raw_url for x in apprise_urls]
    log_lines = []

    with (
        apprise.LogCapture(level=10, fmt="%(levelname)-7s - %(message)s") as capture,
        tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir,
    ):
        temp_dir = Path(temp_dir)
        assert isinstance(capture, StringIO)
        temp_main_log = temp_dir / main_log.name
        notifications_to_send = {
            "no_logs": {"body": text.plain},
            "attach_logs": {"body": text.plain},
            "simplified": {},
        }
        attach_file_failed_msg = "Unable to get copy of main log file. 'attach_logs' URLs will be proccessed without it"
        log_lines = [LogLine(LogLevel.ERROR, attach_file_failed_msg)]
        try:
            shutil.copy(main_log, temp_main_log)
            notifications_to_send["attach_logs"]["attach"] = str(temp_main_log.resolve())
        except OSError:
            log(attach_file_failed_msg, 40)

        for tag, extras in notifications_to_send.items():
            msg = DEFAULT_APPRISE_MESSAGE | extras
            results[tag] = await apprise_obj.async_notify(**msg, tag=tag)
        apprise_logs = capture.getvalue()

    result, new_log_lines = _process_results(all_urls, results, apprise_logs)
    return result, log_lines + new_log_lines
