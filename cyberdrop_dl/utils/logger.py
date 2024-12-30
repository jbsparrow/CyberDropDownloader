from __future__ import annotations

import logging
from pathlib import Path

from rich.console import Console
from rich.text import Text

from cyberdrop_dl.utils import constants

logger = logging.getLogger("cyberdrop_dl")
logger_debug = logging.getLogger("cyberdrop_dl_debug")
console = Console()

ERROR_PREFIX = "\n[bold red]ERROR: [/bold red]"
USER_NAME = Path.home().resolve().parts[-1]


class RedactedConsole(Console):
    def _render_buffer(self, buffer) -> str:
        output: str = super()._render_buffer(buffer)
        return _redact_message(output)


def log(message: Exception | str, level: int = 10, *, sleep: int | None = None, **kwargs) -> None:
    """Simple logging function."""
    logger.log(level, message, **kwargs)
    log_debug(message, level, **kwargs)


def log_debug(message: Exception | str, level: int = 10, **kwargs) -> None:
    """Simple logging function."""
    if constants.DEBUG_VAR:
        message = str(message)
        logger_debug.log(level, message.encode("ascii", "ignore").decode("ascii"), **kwargs)


def log_with_color(message: str, style: str, level: int, show_in_stats: bool = True, **kwargs) -> None:
    """Simple logging function with color."""
    log(message, level, **kwargs)
    text = Text(message, style=style)
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
