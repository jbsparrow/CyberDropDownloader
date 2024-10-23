import traceback
from contextlib import asynccontextmanager

from rich.live import Live

from cyberdrop_dl.managers.console_manager import console
from cyberdrop_dl.utils.utilities import log


class LiveManager:
    def __init__(self, manager):
        self.manager = manager
        self.live = Live(auto_refresh=True,
                        refresh_per_second=self.manager.config_manager.global_settings_data['UI_Options'][
                            'refresh_rate'], console=console)

    @asynccontextmanager
    async def get_main_live(self, stop=False):
        try:
            if self.manager.args_manager.no_ui:
                yield
            else:
                self.live.start()
                self.live.update(self.manager.progress_manager.layout, refresh=True)
                yield self.live
            if stop:
                self.live.stop()
        except Exception as e:
            await log(f"Issue with rich live {e}", level=10, exc_info=True)

    @asynccontextmanager
    async def get_remove_file_via_hash_live(self, stop=False):
        try:
            if self.manager.args_manager.no_ui:
                yield
            else:
                self.live.start()
                self.live.update(self.manager.progress_manager.hash_remove_layout, refresh=True)
                yield
            if stop:
                self.live.stop()
        except Exception as e:
            await log(f"Issue with rich live {e}", level=10, exc_info=True)

    @asynccontextmanager
    async def get_hash_live(self, stop=False):
        try:
            if self.manager.args_manager.no_ui:
                yield
            else:
                self.live.start()
                self.live.update(self.manager.progress_manager.hash_layout, refresh=True)
                yield
            if stop:
                self.live.stop()
        except Exception as e:
            await log(f"Issue with rich live {e}", level=10, exc_info=True)

    @asynccontextmanager
    async def get_sort_live(self, stop=False):
        try:
            if self.manager.args_manager.no_ui:
                yield
            else:
                self.live.start()
                self.live.update(self.manager.progress_manager.sort_layout, refresh=True)
                yield
            if stop:
                self.live.stop()
        except Exception as e:
            await log(f"Issue with rich live {e}", level=10, exc_info=True)
