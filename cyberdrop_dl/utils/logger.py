from __future__ import annotations

import logging

import rich
from rich.text import Text

from cyberdrop_dl.managers.console_manager import log as log_console
from cyberdrop_dl.utils.constants import CONSOLE_DEBUG_VAR, DEBUG_VAR, DEFAULT_CONSOLE_WIDTH

logger = logging.getLogger("cyberdrop_dl")
logger_debug = logging.getLogger("cyberdrop_dl_debug")


def log(message: Exception | str, level: int = 10, sleep: int | None = None, **kwargs) -> None:
    """Simple logging function."""
    logger.log(level, message, **kwargs)
    if DEBUG_VAR:
        logger_debug.log(level, message, **kwargs)
    log_console(level, message, sleep=sleep)


def log_debug(message: Exception | str, level: int = 10, *kwargs) -> None:
    """Simple logging function."""
    if DEBUG_VAR:
        message = str(message)
        logger_debug.log(level, message.encode("ascii", "ignore").decode("ascii"), *kwargs)


def log_debug_console(message: Exception | str, level: int, sleep: int | None = None) -> None:
    if CONSOLE_DEBUG_VAR:
        message = str(message)
        log_console(level, message.encode("ascii", "ignore").decode("ascii"), sleep=sleep)


def log_with_color(message: str, style: str, level: int, show_in_stats: bool = True, *kwargs) -> None:
    """Simple logging function with color."""
    global LOG_OUTPUT_TEXT
    logger.log(level, message, *kwargs)
    text = Text(message, style=style)
    if DEBUG_VAR:
        logger_debug.log(level, message, *kwargs)
    rich.print(text)
    if show_in_stats:
        LOG_OUTPUT_TEXT.append_text(text.append("\n"))


def get_log_output_text() -> str:
    return LOG_OUTPUT_TEXT


def set_log_output_text(text: Text | str) -> None:
    global LOG_OUTPUT_TEXT
    if isinstance(text, str):
        text = Text(text)
    LOG_OUTPUT_TEXT = text


def log_spacer(level: int, char: str = "-") -> None:
    global LOG_OUTPUT_TEXT
    spacer = char * min(int(DEFAULT_CONSOLE_WIDTH / 2), 50)
    rich.print("")
    LOG_OUTPUT_TEXT.append("\n", style="black")
    logger.log(level, spacer)
    if DEBUG_VAR:
        logger_debug.log(level, spacer)
