from __future__ import annotations

import json
from typing import TYPE_CHECKING

import apprise
import rich
from pydantic import ValidationError
from rich.text import Text

from cyberdrop_dl.config_definitions.custom_types import AppriseURL
from cyberdrop_dl.utils import constants
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.yaml import handle_validation_error

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager

DEFAULT_APPRISE_MESSAGE = {
    "body": "Finished downloading. Enjoy :)",
    "title": "Cyberdrop-DL",
    "body_format": apprise.NotifyFormat.TEXT,
}


def is_special_url(url: str) -> bool:
    return (key in url for key in ("windows://",))


def get_apprise_urls(manager: Manager) -> list[AppriseURL] | None:
    apprise_file = manager.path_manager.config_folder / manager.config_manager.loaded_config / "apprise.txt"
    if not apprise_file.is_file():
        return

    try:
        with apprise_file.open(encoding="utf8") as file:
            return [AppriseURL(url=line.strip()) for line in file]

    except ValidationError as e:
        sources = {"AppriseURL": apprise_file}
        handle_validation_error(e, sources=sources)
        return


def process_results(results_dict: dict[str, bool | None]) -> None:
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
    results_dict = {f"Apprise notifications results: {final_result}": results_dict}
    if all(results):
        return
    log(json.dumps(results_dict, indent=4))


def send_apprise_notifications(manager: Manager) -> None:
    apprise_urls = get_apprise_urls(manager)
    if not apprise_urls:
        return

    rich.print("\nSending notifications.. ")
    text: Text = constants.LOG_OUTPUT_TEXT
    constants.LOG_OUTPUT_TEXT = Text("")

    apprise_obj = apprise.Apprise()
    for apprise_url in apprise_urls:
        url = str(apprise_url.url.get_secret_value())
        if is_special_url(url):
            apprise_obj.add(url, tag="simplified")
            continue
        apprise_obj.add(url, tag=apprise_url.tags)

    results = {}
    message = DEFAULT_APPRISE_MESSAGE | {"body": text.plain}
    results["no_log"] = apprise_obj.notify(**message, tag="no_logs")

    message = message | {"attach": str(manager.path_manager.main_log.resolve())}
    results["attach_log"] = apprise_obj.notify(**message, tag="attach_logs")
    results["simplified"] = apprise_obj.notify(**DEFAULT_APPRISE_MESSAGE, tag="simplified")

    process_results(results)
