from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import questionary
from rich.console import Console
from rich.text import Text

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable


_PROMP_STYLE = questionary.Style(
    [
        ("qmark", "fg:#FF9D00 bold"),
        ("question", "bold"),
        ("pointer", "fg:#2196f3 bold"),
        ("highlighted", "fg:#2196f3 "),
        ("selected", "fg:#cc5454"),
        ("disabled", "fg:#858585 italic"),
        ("answer", "fg:#2196f3 bold"),
    ]
)

_ERROR = Text("ERROR:  ", style="bold red")
_WARNING = Text("WARNING:", style="bold yellow")


class _ConsoleWrapper:
    def __init__(self, console: Console | None = None) -> None:
        self.console: Console = console or Console()

    def info(self, *objects: object) -> None:
        self.console.print(*objects)

    def warning(self, *objects: object) -> None:
        self.console.print(_WARNING, *objects)

    def error(self, *objects: object) -> None:
        self.console.print(_ERROR, *objects)

    def rule(self, color: str = "blue") -> None:
        self.console.rule(style=color)

    def line(self, count: int = 1) -> None:
        self.console.line(count)

    def input(self, msg: str = "") -> str:
        return self.console.input(msg)

    def clear(self) -> None:
        _ = os.system("cls" if os.name == "nt" else "clear")  # noqa: S605


console = _ConsoleWrapper()


def enter_to_continue() -> None:
    if "pytest" in sys.modules:
        return
    console.rule()
    console.input("Press <ENTER> to continue")


def ask_choices(choices: Iterable[str]) -> str:
    return questionary.select("What would you like to do", choices=tuple(choices), style=_PROMP_STYLE).unsafe_ask()


def ask_text(text: str, default: str = "") -> str:
    return questionary.text(text, default=default, style=_PROMP_STYLE).unsafe_ask()


def ask_confirmation(text: str = "", *, explicit: bool = False) -> bool:
    if explicit:
        msg = "Type 'YES' to proceed: "
        if text and not text.endswith("?"):
            text += "?"
        answer = console.input(f"{text}. {msg}" if text else msg)
        return answer.strip().casefold() == "yes"
    return questionary.confirm(text, default=False, style=_PROMP_STYLE).unsafe_ask()


def ask_dir(message: str = "Select dir path", default: Path | None = None) -> Path:

    def is_dir(path: Path) -> None:
        if not path.is_dir():
            raise NotADirectoryError(str(path))

    return ask_path(message, default, validate=is_dir, only_dir=True)


def ask_path(
    message: str = "Select path",
    default: Path | None = None,
    *,
    validate: Callable[[Path], None] | None = None,
    must_exists: bool = True,
    only_dir: bool = False,
) -> Path:
    while True:
        try:
            answer = questionary.path(
                message, default=str(default or Path.home()), only_directories=only_dir, style=_PROMP_STYLE
            ).unsafe_ask()
            path = Path(answer).expanduser()
            if must_exists and not path.exists():
                raise FileNotFoundError(answer)
            if validate:
                validate(path)

        except OSError as e:
            console.error(repr(e))
        else:
            return path.resolve()


def ask_should_create_config(file: Path) -> bool:
    console.warning("A default config file does not exists")
    return ask_confirmation(f"Do you want to create it at '{file}'?")


def ask_should_create_folder(folder: Path) -> bool:
    console.warning(f"Folder '{folder}' does not exists")
    return ask_confirmation("Do you want to create it?")


def ask_should_use_retry_path() -> bool:
    return ask_confirmation("Do you want to use the exact same download path as the original attempt?")
