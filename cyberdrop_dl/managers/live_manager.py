from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from rich.live import Live
from rich.progress import Progress, SpinnerColumn, TextColumn

from cyberdrop_dl.utils.logger import console

if TYPE_CHECKING:
    from collections.abc import Generator

    from rich.layout import Layout

    from cyberdrop_dl.managers.manager import Manager


class LiveManager:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.no_ui = self.manager.parsed_args.cli_only_args.no_ui
        self.live = Live(
            auto_refresh=True,
            refresh_per_second=self.manager.config_manager.global_settings_data.ui_options.refresh_rate,
            console=console,
            transient=True,
            screen=not self.no_ui,
        )

        self.placeholder = Progress(
            SpinnerColumn(style="green", spinner_name="dots"),
            TextColumn("Running Cyberdrop-DL"),
        )
        self.placeholder.add_task("running with no UI", total=100, completed=0)

    @contextmanager
    def get_live(self, layout: Layout, stop: bool = False) -> Generator[Live]:
        show = self.placeholder if self.no_ui else layout
        try:
            self.live.start()
            self.live.update(show, refresh=True)
            yield self.live
        finally:
            if stop:
                self.live.stop()

    @contextmanager
    def get_main_live(self, stop: bool = False) -> Generator[Live]:
        """Main UI startup and context manager."""
        layout = self.manager.progress_manager.layout
        with self.get_live(layout, stop=stop) as live:
            yield live

    @contextmanager
    def get_remove_file_via_hash_live(self, stop: bool = False) -> Generator[Live]:
        layout = self.manager.progress_manager.hash_remove_layout
        with self.get_live(layout, stop=stop) as live:
            yield live

    @contextmanager
    def get_hash_live(self, stop: bool = False) -> Generator[Live]:
        layout = self.manager.progress_manager.hash_layout
        with self.get_live(layout, stop=stop) as live:
            yield live

    @contextmanager
    def get_sort_live(self, stop: bool = False) -> Generator[Live]:
        layout = self.manager.progress_manager.sort_layout
        with self.get_live(layout, stop=stop) as live:
            yield live
