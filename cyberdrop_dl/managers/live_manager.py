from __future__ import annotations

import asyncio
from contextlib import contextmanager
from functools import partialmethod
from typing import TYPE_CHECKING

from rich.live import Live

from cyberdrop_dl import constants
from cyberdrop_dl.utils.args import is_terminal_in_portrait

if TYPE_CHECKING:
    from collections.abc import Generator

    from rich.console import RenderableType

    from cyberdrop_dl.managers.manager import Manager


class LiveManager:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.ui_setting = self.manager.parsed_args.cli_only_args.ui
        self.fullscreen = f = self.manager.parsed_args.cli_only_args.fullscreen_ui
        self.refresh_rate = rate = self.manager.config_manager.global_settings_data.ui_options.refresh_rate
        self.live = Live(refresh_per_second=rate, transient=True, screen=f, auto_refresh=True)
        self.current_layout: str

    @contextmanager
    def get_live(self, name: str, stop: bool = False) -> Generator[Live | None]:
        layout = self.get_layout(name)
        with self.live_context_manager(layout, stop=stop) as live:
            yield live

    get_sort_live = partialmethod(get_live, name="sort_layout")
    get_main_live = partialmethod(get_live, name="main_layout")
    get_hash_live = partialmethod(get_live, name="hash_layout")
    get_remove_file_via_hash_live = partialmethod(get_live, name="hash_remove_layout")

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #

    def get_layout(self, name: str) -> RenderableType | None:
        if name == "main_layout":
            name = f"{self.ui_setting.value}_layout"
            self.current_layout = name
        return getattr(self.manager.progress_manager, name, None)

    async def watch_orientation(self, stop_event: asyncio.Event) -> None:
        """Watches for screen orientation changes and updates the live display accordingly."""
        while not stop_event.is_set():
            new_layout = "vertical_layout" if is_terminal_in_portrait() else "horizontal_layout"
            if new_layout != self.current_layout:
                self.current_layout = new_layout
                layout = self.get_layout(new_layout)
                self.live.update(layout, refresh=True)  # type: ignore[reportArgumentType]
            await asyncio.sleep(0.5)

    @contextmanager
    def live_context_manager(self, layout: RenderableType | None, stop: bool = False) -> Generator[Live | None]:
        stop_event = asyncio.Event()
        orientation_task = None
        og_console = constants.console_handler.console
        try:
            constants.console_handler.console = self.live.console
            self.live.start()
            if layout:
                self.live.update(layout, refresh=True)
                if self.current_layout in ("vertical_layout", "horizontal_layout"):
                    orientation_task = asyncio.create_task(self.watch_orientation(stop_event))
            yield self.live
        finally:
            constants.console_handler.console = og_console
            stop_event.set()
            if orientation_task:
                orientation_task.cancel()
            if stop:
                self.live.update("")
                self.live.stop()
