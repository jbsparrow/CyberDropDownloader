from __future__ import annotations

import contextlib
import json
import logging
import queue
import sys
from functools import wraps
from logging.handlers import QueueHandler, QueueListener
from pathlib import Path
from typing import IO, TYPE_CHECKING, ParamSpec

from rich._log_render import LogRender
from rich.console import Console, Group
from rich.containers import Lines, Renderables
from rich.logging import RichHandler
from rich.measure import Measurement
from rich.padding import Padding
from rich.text import Text, TextType

from cyberdrop_dl import constants, env
from cyberdrop_dl.dependencies import browser_cookie3
from cyberdrop_dl.exceptions import InvalidYamlError

logger = logging.getLogger("cyberdrop_dl")
logger_debug = logging.getLogger("cyberdrop_dl_debug")
startup_logger = logging.getLogger("cyberdrop_dl_startup")
_DEFAULT_CONSOLE = Console()

_USER_NAME = Path.home().resolve().name
_NEW_ISSUE_URL = "https://github.com/jbsparrow/CyberDropDownloader/issues/new/choose"


if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable
    from datetime import datetime

    from rich.console import ConsoleRenderable

    from cyberdrop_dl.managers.manager import Manager

    _P = ParamSpec("_P")
    _ExitCode = str | int | None


class RedactedConsole(Console):
    """Custom console to remove username from logs"""

    def _render_buffer(self, buffer) -> str:
        output: str = super()._render_buffer(buffer)
        return _redact_message(output)


class JsonLogRecord(logging.LogRecord):
    def getMessage(self) -> str:  # noqa: N802
        """`dicts` will be logged as json, lazily"""

        msg = str(self._proccess_msg(self.msg))
        if self.args:
            args = map(self._proccess_msg, self.args)
            try:
                return msg.format(*args)
            except Exception:
                return msg % args

        return msg

    @staticmethod
    def _proccess_msg(msg: object) -> object:
        # TODO: Use our custom decoder to support more types
        if isinstance(msg, dict):
            return json.dumps(msg, indent=2, ensure_ascii=False, default=str)
        return msg


logging.setLogRecordFactory(JsonLogRecord)


class LogHandler(RichHandler):
    """Rich Handler with default settings, automatic console creation and custom log render to remove padding in files."""

    def __init__(
        self, level: int = 10, file: IO[str] | None = None, width: int | None = None, debug: bool = False, **kwargs
    ) -> None:
        is_file: bool = file is not None
        redacted: bool = is_file and not debug
        console_cls = RedactedConsole if redacted else Console
        if file is None and width is None:
            console = _DEFAULT_CONSOLE
        else:
            console = console_cls(file=file, width=width)
        options = constants.RICH_HANDLER_DEBUG_CONFIG if debug else constants.RICH_HANDLER_CONFIG
        options = options | kwargs
        super().__init__(level, console, show_time=is_file, **options)
        if is_file:
            self._log_render = NoPaddingLogRender(show_level=True)


class BareQueueHandler(QueueHandler):
    """Sends the log record to the queue as is.

    The base class formats the record by merging the message and arguments.
    It also removes all other attributes of the record, just in case they have not pickleable objects.

    This made tracebacks render improperly because when the rich handler picks the log record from the queue, it has no traceback.
    The original traceback was being formatted as normal text and included as part of the message.

    Having not pickleable objects is only an issue in multi-processing operations (multiprocessing.Queue)
    """

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        return record


class QueuedLogger:
    """A helper class to setup a queue handler + listener."""

    def __init__(self, manager: Manager, split_handler: LogHandler, name: str = "main") -> None:
        assert name not in manager.loggers, f"A logger with the name '{name}' already exists"
        log_queue = queue.Queue()
        self.handler = BareQueueHandler(log_queue)
        self.log_handler = split_handler
        self.listener = QueueListener(log_queue, split_handler, respect_handler_level=True)
        self.listener.start()
        manager.loggers[name] = self

    def stop(self) -> None:
        """This asks the thread to terminate, and waits until all pending messages are processed."""
        self.listener.stop()
        self.handler.close()
        self.log_handler.console.file.close()
        self.log_handler.close()


class NoPaddingLogRender(LogRender):
    cdl_padding: int = 0
    EXCLUDE_PATH_LOGGING_FROM: tuple[str, ...] = "logger.py", "base.py", "session.py", "cache_control.py"

    def __call__(  # type: ignore[reportIncompatibleMethodOverride]
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
            self.cdl_padding = _get_renderable_length(output)

        if self.show_path and path and not any(path.startswith(p) for p in self.EXCLUDE_PATH_LOGGING_FROM):
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
                renderable = _indent_text(renderable, console, self.cdl_padding)
                renderable.stylize("log.message")
                output.append(renderable)
                continue
            padded_lines.append(Padding(renderable, (0, 0, 0, self.cdl_padding), expand=False))

        return Group(output, *padded_lines)


def _get_renderable_length(renderable) -> int:
    measurement = Measurement.get(_DEFAULT_CONSOLE, _DEFAULT_CONSOLE.options, renderable)
    return measurement.maximum


def _indent_text(text: Text, console: Console, indent: int = 30) -> Text:
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


def log(message: object, level: int = 10, bug: bool = False, **kwargs) -> None:
    """Simple logging function."""
    log_debug(message, level, **kwargs)
    if bug:
        args = message, f"Please open a bug report at {_NEW_ISSUE_URL}"
        message = "{}. {}"
        level = 30
    else:
        args = ()
    logger.log(level, message, *args, **kwargs)


def log_debug(message: object, level: int = 10, **kwargs) -> None:
    """Simple logging function."""
    if env.DEBUG_VAR:
        logger_debug.log(level, message, **kwargs)


def log_with_color(message: Text | str, style: str, level: int = 20, show_in_stats: bool = True, **kwargs) -> None:
    """Simple logging function with color."""
    text = message if isinstance(message, Text) else Text(message, style=style)
    log(text.plain, level, **kwargs)
    if constants.CONSOLE_LEVEL >= 50 and "pytest" not in sys.modules:
        _DEFAULT_CONSOLE.print(text)
    if show_in_stats:
        constants.LOG_OUTPUT_TEXT.append_text(text.append("\n"))


def log_spacer(level: int, char: str = "-", *, log_to_console: bool = True, log_to_file: bool = True) -> None:
    spacer = char * min(int(constants.DEFAULT_CONSOLE_WIDTH / 2), 50)
    if log_to_file:
        log(spacer, level)
    if log_to_console and constants.CONSOLE_LEVEL >= 50:
        _DEFAULT_CONSOLE.print("")
    constants.LOG_OUTPUT_TEXT.append("\n", style="black")


def _redact_message(message: Exception | Text | str) -> str:
    redacted = str(message)
    separators = ["\\", "\\\\", "/"]
    for sep in separators:
        as_tail = sep + _USER_NAME
        as_part = _USER_NAME + sep
        redacted = redacted.replace(as_tail, f"{sep}[REDACTED]").replace(as_part, f"[REDACTED]{sep}")
    return redacted


@contextlib.contextmanager
def _setup_startup_logger() -> Generator[None]:
    """Context manager to add a file handler to the startup logger

    It will only add it if we have an exception, to prevent creating an empty file"""
    startup_logger.setLevel(10)
    if "pytest" not in sys.modules:
        console_handler = LogHandler(level=10)
        startup_logger.addHandler(console_handler)
    try:
        yield

    except Exception:
        try:
            file = Path.cwd() / "startup.log"
            file_handler = LogHandler(
                level=10,
                file=file.open("w", encoding="utf8"),
                width=constants.DEFAULT_CONSOLE_WIDTH,
            )
            startup_logger.addHandler(file_handler)
        except OSError:
            # We could not create the file for some reason
            # Ignore this and just log to the console
            pass
        raise


def catch_exceptions(func: Callable[_P, _ExitCode]) -> Callable[_P, _ExitCode]:
    """Decorator to automatically log uncaught exceptions.

    Exceptions will be logged to a file in the current working directory
    because the manager setup itself may have failed, therefore we don't know
    what the proper log file path is.
    """

    @wraps(func)
    def catch(*args, **kwargs) -> _ExitCode | None:
        try:
            with _setup_startup_logger():
                return func(*args, **kwargs)

        except InvalidYamlError as e:
            startup_logger.error(e.message)

        except browser_cookie3.BrowserCookieError:
            startup_logger.exception("")

        except OSError as e:
            startup_logger.exception(str(e))

        except KeyboardInterrupt:
            startup_logger.info("Exiting...")
            return

        except Exception:
            msg = "An error occurred, please report this to the developer with your logs file:"
            startup_logger.exception(msg)

        return 1

    return catch
