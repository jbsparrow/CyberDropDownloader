from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from rich._log_render import LogRender
from rich.console import Console, Group
from rich.containers import Lines, Renderables
from rich.measure import Measurement
from rich.padding import Padding
from rich.text import Text, TextType

from cyberdrop_dl import env
from cyberdrop_dl.utils import constants

logger = logging.getLogger("cyberdrop_dl")
logger_debug = logging.getLogger("cyberdrop_dl_debug")
console = Console()

ERROR_PREFIX = "\n[bold red]ERROR: [/bold red]"
USER_NAME = Path.home().resolve().parts[-1]


if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from datetime import datetime

    from rich.console import ConsoleRenderable
    from rich.logging import RichHandler


EXCLUDE_PATH_LOGGING_FROM = "logger.py", "base.py", "session.py", "cache_control.py"


class NoPaddingLogRender(LogRender):
    cdl_padding = 0

    def __call__(
        self,
        console: Console,
        renderables: Iterable[ConsoleRenderable],
        log_time: datetime | None = None,
        time_format: str | Callable[[datetime], Text] | None = None,
        level: TextType = "",
        path: str | None = None,
        line_no: int | None = None,
        link_path: str | None = None,
    ):
        output = Text(no_wrap=True)
        if self.show_time:
            log_time = log_time or console.get_datetime()
            time_format = time_format or self.time_format
            log_time_display = (
                time_format(log_time)
                if callable(time_format)
                else Text(log_time.strftime(time_format), style="log.time")
            )
            if log_time_display == self._last_time and self.omit_repeated_times:
                output.append(" " * len(log_time_display), style="log.time")
                output.pad_right(1)
            else:
                output.append(log_time_display)
                output.pad_right(1)
                self._last_time = log_time_display
        if self.show_level:
            output.append(level)
            output.pad_right(1)

        if not self.cdl_padding:
            self.cdl_padding = get_renderable_length(output)

        if self.show_path and path and not any(path.startswith(p) for p in EXCLUDE_PATH_LOGGING_FROM):
            path_text = Text(style="log.path")
            path_text.append(path, style=f"link file://{link_path}" if link_path else "")
            if line_no:
                path_text.append(":")
                path_text.append(
                    f"{line_no}",
                    style=f"link file://{link_path}#{line_no}" if link_path else "",
                )
            output.append(path_text)
            output.pad_right(1)

        padded_lines: list[ConsoleRenderable] = []

        for renderable in Renderables(renderables):  # type: ignore
            if isinstance(renderable, Text):
                renderable = indent_text(renderable, console, self.cdl_padding)
                renderable.stylize("log.message")
                output.append(renderable)
                continue
            padded_lines.append(Padding(renderable, (0, 0, 0, self.cdl_padding), expand=False))

        output = Group(output, *padded_lines)
        return output


def get_renderable_length(renderable) -> int:
    measurement = Measurement.get(console, console.options, renderable)
    return measurement.maximum


def indent_text(text: Text, console: Console, indent: int = 30) -> Text:
    """Indents each line of a Text object except the first one."""
    indent_str = Text("\n" + (" " * indent))
    new_text = Text()
    new_width = console.width - indent
    lines: Lines = text.wrap(console, width=new_width)
    first_line = lines[0]
    other_lines = lines[1:]
    for line in other_lines:
        line.rstrip()
        new_text.append(indent_str + line)
    first_line.rstrip()
    return first_line.append(new_text)


def add_custom_log_render(rich_handler: RichHandler) -> None:
    rich_handler._log_render = NoPaddingLogRender(
        omit_repeated_times=True,
        show_time=True,
        show_level=True,
        show_path=True,
    )


class RedactedConsole(Console):
    def _render_buffer(self, buffer) -> str:
        output: str = super()._render_buffer(buffer)
        return _redact_message(output)


def process_log_msg(message: dict | Exception | str) -> str:
    if isinstance(message, dict):
        return json.dumps(message, indent=4, ensure_ascii=False)
    return str(message)


def log(message: dict | Exception | str, level: int = 10, **kwargs) -> None:
    """Simple logging function."""
    msg = process_log_msg(message)
    logger.log(level, msg, **kwargs)
    log_debug(msg, level, **kwargs)


def log_debug(message: dict | Exception | str, level: int = 10, **kwargs) -> None:
    """Simple logging function."""
    if env.DEBUG_VAR:
        msg = process_log_msg(message)
        logger_debug.log(level, msg, **kwargs)


def log_with_color(message: Text | str, style: str, level: int = 20, show_in_stats: bool = True, **kwargs) -> None:
    """Simple logging function with color."""
    text = message if isinstance(message, Text) else Text(message, style=style)
    log(text.plain, level, **kwargs)
    if constants.CONSOLE_LEVEL >= 50:
        console.print(text)
    if show_in_stats:
        constants.LOG_OUTPUT_TEXT.append_text(text.append("\n"))


def log_spacer(level: int, char: str = "-", *, log_to_console: bool = True, log_to_file: bool = True) -> None:
    spacer = char * min(int(constants.DEFAULT_CONSOLE_WIDTH / 2), 50)
    if log_to_file:
        log(spacer, level)
    if log_to_console and constants.CONSOLE_LEVEL >= 50:
        console.print("")
    constants.LOG_OUTPUT_TEXT.append("\n", style="black")


def _redact_message(message: Exception | Text | str) -> str:
    redacted = str(message)
    separators = ["\\", "\\\\", "/"]
    for sep in separators:
        as_tail = sep + USER_NAME
        as_part = USER_NAME + sep
        redacted = redacted.replace(as_tail, f"{sep}[REDACTED]").replace(as_part, f"[REDACTED]{sep}")
    return redacted
