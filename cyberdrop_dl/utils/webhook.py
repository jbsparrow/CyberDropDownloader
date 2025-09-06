from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

import aiofiles
import rich
from aiohttp import FormData

from cyberdrop_dl import constants
from cyberdrop_dl.utils import aio
from cyberdrop_dl.utils.logger import log, log_debug, log_spacer

if TYPE_CHECKING:
    from pathlib import Path

    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.models.base_models import HttpAppriseURL


_DEFAULT_DIFF_LINE_FORMAT: str = "{}"
_STYLE_TO_DIFF_MAP = {
    "green": "+   {}",
    "red": "-   {}",
    "yellow": "*** {}",
}


def _prepare_diff_text() -> str:
    """Returns the `rich.text` in the current log buffer as a plain str with diff syntax."""

    def prepare_lines():
        for text_line in constants.LOG_OUTPUT_TEXT.split(allow_blank=True):
            line_str = text_line.plain.rstrip("\n")
            first_span = text_line.spans[0] if text_line.spans else None
            style: str = str(first_span.style) if first_span else ""

            color = style.split(" ")[0] or "black"  # remove console hyperlink markup (if any)
            line_format: str = _STYLE_TO_DIFF_MAP.get(color) or _DEFAULT_DIFF_LINE_FORMAT
            yield line_format.format(line_str)

    return "\n".join(prepare_lines())


async def _prepare_form(webhook: HttpAppriseURL, main_log: Path) -> FormData:
    diff_text = _prepare_diff_text()
    form = FormData()

    if "attach_logs" in webhook.tags and (size := await aio.get_size(main_log)):
        if size <= 25 * 1024 * 1024:  # 25MB
            async with aiofiles.open(main_log, "rb") as f:
                form.add_field("file", await f.read(), filename=main_log.name)

        else:
            diff_text += "\n\nWARNING: log file too large to send as attachment\n"

    form.add_fields(
        ("content", f"```diff\n{diff_text}```"),
        ("username", "CyberDrop-DL"),
    )
    return form


async def send_webhook_message(manager: Manager) -> None:
    """Outputs the stats to a code block for webhook messages."""
    webhook = manager.config_manager.settings_data.logs.webhook

    if not webhook:
        return

    rich.print("\nSending Webhook Notifications.. ")
    url = cast("AbsoluteHttpURL", webhook.url.get_secret_value())
    form = await _prepare_form(webhook, manager.path_manager.main_log)

    async with manager.client_manager._new_session() as session, session.post(url, data=form) as response:
        result = [constants.NotificationResult.SUCCESS.value]
        result_to_log = result
        if not response.ok:
            json_resp: dict[str, Any] = await response.json()
            if "content" in json_resp:
                json_resp.pop("content")
            resp_text = json.dumps(json_resp, indent=4, ensure_ascii=False)
            result_to_log = constants.NotificationResult.FAILED.value, resp_text

    log_spacer(10, log_to_console=False)
    rich.print("Webhook Notifications Results:", *result)
    logger = log_debug if response.ok else log
    result_to_log = "\n".join(map(str, result_to_log))
    logger(f"Webhook Notifications Results: {result_to_log}")
