from __future__ import annotations

from contextlib import contextmanager
from functools import partialmethod
from typing import TYPE_CHECKING

from rich.live import Live
from rich.progress import Progress, SpinnerColumn, TextColumn

from cyberdrop_dl.utils import constants
from cyberdrop_dl.utils.logger import console

if TYPE_CHECKING:
    from collections.abc import Generator

    from rich.console import RenderableType

    from cyberdrop_dl.managers.manager import Manager


class LiveManager:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.no_ui = self.manager.parsed_args.cli_only_args.no_ui
        refresh_rate = self.manager.config_manager.global_settings_data.ui_options.refresh_rate
        self.live = Live(refresh_per_second=refresh_rate, console=console, transient=True, screen=not self.no_ui)
        spinner = SpinnerColumn(style="green", spinner_name="dots"), TextColumn("Running Cyberdrop-DL")
        self.placeholder = Progress(*spinner)
        self.placeholder.add_task("running with no UI", total=100, completed=0)

    @contextmanager
    def get_live(self, name: str, stop: bool = False) -> Generator[Live | None]:
        layout = self.get_layout(name)
        with self.live_context_manager(layout, stop=stop) as live:
            yield live

    get_sort_live = partialmethod(get_live, name="sort_layout")
    get_main_live = partialmethod(get_live, name="main_runtime_layout")
    get_hash_live = partialmethod(get_live, name="hash_layout")
    get_remove_file_via_hash_live = partialmethod(get_live, name="hash_remove_layout")

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #

    def get_layout(self, name: str) -> RenderableType:
        layout = getattr(self.manager.progress_manager, name, None)
        if not layout:
            raise ValueError
        return self.placeholder if self.no_ui else layout

    @contextmanager
    def live_context_manager(self, layout: RenderableType, stop: bool = False) -> Generator[Live | None]:
        try:
            self.live.start()
            if not (10 <= constants.CONSOLE_LEVEL <= 50):
                self.live.update(layout, refresh=True)
            yield self.live
        finally:
            if stop:
                self.live.stop()
