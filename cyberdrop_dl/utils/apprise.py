from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

import apprise
import rich
from pydantic import ValidationError
from rich.text import Text

from cyberdrop_dl.config_definitions.custom_types import AppriseURLModel
from cyberdrop_dl.utils import constants
from cyberdrop_dl.utils.logger import log, log_debug
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


OS_URLS = ["windows://"]


def get_apprise_urls(manager: Manager) -> list[AppriseURLModel] | None:
    apprise_file = manager.path_manager.config_folder / manager.config_manager.loaded_config / "apprise.txt"
    if not apprise_file.is_file():
        return

    try:
        with apprise_file.open(encoding="utf8") as file:
            return simplify_urls([AppriseURLModel(url=line.strip()) for line in file])

    except ValidationError as e:
        sources = {"AppriseURL": apprise_file}
        handle_validation_error(e, sources=sources)
        return


def simplify_urls(apprise_urls: list[AppriseURLModel]) -> list[AppriseURL]:
    final_urls = []

    def is_special_url(url: str) -> bool:
        special_urls = OS_URLS
        return any(key in url for key in special_urls)

    for apprise_url in apprise_urls:
        url = str(apprise_url.url.get_secret_value())
        tags = apprise_url.tags or ["no_logs"]
        if is_special_url(url):
            tags = ["simplified"]
        entry = AppriseURL(url=url, tags=tags)
        final_urls.append(entry)
    return sorted(final_urls, key=lambda x: x.url)


def process_results(results_dict: dict[str, bool | None], apprise_logs: str) -> None:
    results = [r for r in results_dict.values() if r is not None]
    if not results:
        final_result = Text("No notifications sent", "yellow")
    if all(results):
        final_result = Text("Success", "green")
    elif any(results):
        final_result = Text("Partial Success", "yellow")
    else:
        final_result = Text("Failed", "bold red")
    rich.print("Apprise notifications results:", final_result)
    logger = log_debug if all(results) else log
    logger(f"Apprise notifications results: {final_result}")
    logger(json.dumps(results_dict, indent=4))
    reduced_logs = "\n".join(
        [line for line in apprise_logs.splitlines() if "Running Post-Download Processes For Config" not in line]
    )
    logger(reduced_logs)


async def send_apprise_notifications(manager: Manager) -> None:
    apprise_urls = get_apprise_urls(manager)
    if not apprise_urls:
        return

    rich.print("\nSending notifications.. ")
    text: Text = constants.LOG_OUTPUT_TEXT
    constants.LOG_OUTPUT_TEXT = Text("")

    apprise_obj = apprise.Apprise()
    for apprise_url in apprise_urls:
        apprise_obj.add(apprise_url.url, tag=apprise_url.tags)

    results = {}
    main_log = str(manager.path_manager.main_log.resolve())
    message = DEFAULT_APPRISE_MESSAGE | {"body": text.plain}
    apprise_logs = None
    with apprise.LogCapture(level=10, fmt="%(levelname)s - %(message)s") as capture:
        results["no_logs"] = await apprise_obj.async_notify(**message, tag="no_logs")
        results["attach_logs"] = await apprise_obj.async_notify(
            **DEFAULT_APPRISE_MESSAGE, tag="attach_logs", attach=main_log
        )
        results["simplified"] = await apprise_obj.async_notify(**DEFAULT_APPRISE_MESSAGE, tag="simplified")
        apprise_logs = capture.getvalue()

    process_results(results, apprise_logs)
