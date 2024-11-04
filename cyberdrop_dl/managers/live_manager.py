from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from rich.console import Console
from rich.live import Live

from cyberdrop_dl.managers.console_manager import console
from cyberdrop_dl.utils.utilities import log

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from rich.layout import Layout


class LiveManager:
    def __init__(self, manager: Manager):
        self.manager = manager
        self.live = Live(auto_refresh=True,
                        refresh_per_second=self.manager.config_manager.global_settings_data['UI_Options'][
                            'refresh_rate'], console=console)

    @asynccontextmanager
    async def get_live(self, layout: Layout, stop=False):
        try:
            if self.manager.args_manager.no_ui:
                yield
            else:
                self.live.start()
                self.live.update(layout, refresh=True)
                yield self.live
            if stop:
                self.live.stop()
                if not self.manager.args_manager.no_ui:
                    Console().clear()
        except Exception as e:
            await log(f"Issue with rich live {e}", level=10, exc_info=True)

    @asynccontextmanager
    async def get_main_live(self, stop=False):
        "main UI startup and context manager"
        layout = self.manager.progress_manager.layout
        async with self.get_live(layout, stop=stop) as live:
            yield live

    @asynccontextmanager
    async def get_remove_file_via_hash_live(self, stop=False):
        layout = self.manager.progress_manager.hash_remove_layout
        async with self.get_live(layout, stop=stop) as live:
            yield live

    @asynccontextmanager
    async def get_hash_live(self, stop=False):
        layout = self.manager.progress_manager.hash_layout
        async with self.get_live(layout, stop=stop) as live:
            yield live

    @asynccontextmanager
    async def get_sort_live(self, stop=False):
        layout = self.manager.progress_manager.sort_layout
        async with self.get_live(layout, stop=stop) as live:
            yield live
