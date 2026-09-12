from __future__ import annotations

import sys
from contextvars import ContextVar
from typing import TYPE_CHECKING

import aiohttp
from rich.markdown import Markdown

from cyberdrop_dl import __version__, aio, stats
from cyberdrop_dl.constants import USE_RETRY_PATH
from cyberdrop_dl.hasher import Hasher, hash_directory
from cyberdrop_dl.progress import hyperlink
from cyberdrop_dl.prompts import (
    ask_choices,
    ask_confirmation,
    ask_dir,
    ask_should_create_config,
    ask_should_use_retry_path,
    console,
    enter_to_continue,
)
from cyberdrop_dl.scrape_source import RetrySource
from cyberdrop_dl.sorter import Sorter
from cyberdrop_dl.utils import text_editor

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from cyberdrop_dl.manager import Manager

_INPUT_FILE: ContextVar[Path] = ContextVar("_INPUT_FILE")
_CHANGELOG_URL = "https://raw.githubusercontent.com/Cyberdrop-DL/cyberdrop-dl/refs/heads/main/CHANGELOG.md"
_changelog_content: str = ""


def _changelog() -> str:
    global _changelog_content  # noqa: PLW0603
    if not _changelog_content:
        _changelog_content = aio.run(_fetch_changelog())

    return _changelog_content


def run(manager: Manager, input_file: Path) -> RetrySource | Path:
    _INPUT_FILE.set(input_file)
    choices: dict[str, Callable[[Manager], RetrySource | Path | None]] = {
        "Download": lambda _: input_file,
        "Retry failed downloads": _retry_failed,
        "Create file hashes": _scan_and_create_hashes,
        "Sort files in download folder": _sort_files,
        "Edit URLs.txt": lambda _: _edit_urls(),
        "Edit config": _edit_config,
        "View changelog": lambda _: _view_changelog(),
        "Exit": lambda _: sys.exit(0),
    }

    while True:
        _app_header(manager)
        answer = ask_choices(choices)
        source = choices[answer](manager)
        if source:
            return source


def _retry_failed(_: object) -> RetrySource:
    USE_RETRY_PATH.set(ask_should_use_retry_path())
    return RetrySource.FAILED


def _scan_and_create_hashes(manager: Manager) -> None:
    path = ask_dir("Select the directory to scan", default=manager.config.download_folder)
    with Hasher.create(manager.config, manager.database, path) as hasher:
        hash_stats = aio.run(hash_directory(hasher))
        stats.print(hash_stats)
        enter_to_continue()


def _sort_files(manager: Manager) -> None:
    sorter = Sorter.from_config(manager.config)
    console.warning(
        f"You are about to sort files from '{sorter.input_dir}' to '{sorter.output_dir}'",
    )
    if ask_confirmation(explicit=True):
        aio.run(sorter.run())
        enter_to_continue()


def _edit_config(manager: Manager) -> None:
    file = manager.config.source
    if file is None:
        file = manager.appdata.config_file
        if not ask_should_create_config(file):
            return
        type(manager.config)().save_to(file)

    try:
        text_editor.open(file)
    except ValueError as e:
        console.error(str(e))
    else:
        console.warning("You must restart cyberdrop-dl for config changes to take effect")

    enter_to_continue()


def _edit_urls() -> None:
    file = _INPUT_FILE.get()
    if not file.exists():
        file.parent.mkdir(parents=True, exist_ok=True)
        file.touch()
    try:
        text_editor.open(file)
    except ValueError as e:
        console.error(e)

    enter_to_continue()


async def _fetch_changelog() -> str:
    async with aiohttp.request(
        "GET",
        _CHANGELOG_URL,
        raise_for_status=True,
    ) as response:
        return await response.text()


def _view_changelog() -> None:
    console.clear()
    try:
        content = _changelog()
    except Exception as e:  # noqa: BLE001
        console.error("UNABLE TO GET CHANGELOG INFORMATION", repr(e))
        enter_to_continue()
        return

    with console.console.pager(links=True):
        console.info(Markdown(content, justify="left"))


def _app_header(manager: Manager) -> None:
    console.clear()
    console.info(f"[bold]cyberdrop-dl ([blue]v{__version__!s}[/blue])[/bold]")
    console.rule()
    paths = {
        "Config file": manager.config.source,
        "Database file": manager.appdata.db_file,
        "URLs file": _INPUT_FILE.get(),
        "Cache file": manager.appdata.cache_file,
        "Logs": manager.config.logs.effective_log_folder,
        "Main log file": manager.config.logs.files.main,
    }
    padding = max(map(len, paths))
    for name, file in paths.items():
        console.info(f"{name:<{padding}} :", hyperlink(file) if file else None)

    console.line()
