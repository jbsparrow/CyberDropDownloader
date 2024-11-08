from __future__ import annotations

import logging

from rich.console import Console
from rich.text import Text

from cyberdrop_dl.utils import constants

logger = logging.getLogger("cyberdrop_dl")
logger_debug = logging.getLogger("cyberdrop_dl_debug")
console = Console()


def print_to_console(text: Text | str) -> None:
    console.print(text)


def log(message: Exception | str, level: int = 10, *, sleep: int | None = None, **kwargs) -> None:
    """Simple logging function."""
    logger.log(level, message, **kwargs)
    log_debug(message, level, **kwargs)
    log_debug_console(message, level, sleep=sleep)


def log_debug(message: Exception | str, level: int = 10, **kwargs) -> None:
    """Simple logging function."""
    if constants.DEBUG_VAR:
        message = str(message)
        logger_debug.log(level, message.encode("ascii", "ignore").decode("ascii"), **kwargs)


def log_debug_console(message: Exception | str, level: int, sleep: int | None = None) -> None:
    if constants.CONSOLE_DEBUG_VAR:
        message = str(message)
        _log_to_console(level, message.encode("ascii", "ignore").decode("ascii"), sleep=sleep)


def log_with_color(message: str, style: str, level: int, show_in_stats: bool = True, **kwargs) -> None:
    """Simple logging function with color."""
    log(message, level, **kwargs)
    text = Text(message, style=style)
    console.print(text)
    if show_in_stats:
        constants.LOG_OUTPUT_TEXT.append_text(text.append("\n"))


def log_spacer(level: int, char: str = "-") -> None:
    spacer = char * min(int(constants.DEFAULT_CONSOLE_WIDTH / 2), 50)
    log(spacer, level)
    console.print("")
    constants.LOG_OUTPUT_TEXT.append("\n", style="black")


def _log_to_console(level: int, record: str, *_, **__) -> None:
    level = level or 10
    if level >= constants.CONSOLE_LEVEL:
        console.log(record)
