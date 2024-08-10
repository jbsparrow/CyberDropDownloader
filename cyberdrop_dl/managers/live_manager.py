from rich.live import Live
from contextlib import contextmanager



class LiveManager:
    def __init__(self,manager):
        self.manager = manager
        self.live=None
    @contextmanager
    def get_main_live(self):
        if self.manager.args_manager.no_ui:
            yield
        elif self.live:
            self.live.update(Live(self.manager.progress_manager.layout, refresh_per_second=self.manager.config_manager.global_settings_data['UI_Options']['refresh_rate']))
            yield self.live
        else:
            self.live=Live(self.manager.progress_manager.layout, refresh_per_second=self.manager.config_manager.global_settings_data['UI_Options']['refresh_rate'])
            with self.live as live:
                yield live
    @contextmanager
    def get_hash_live(self):
        if self.manager.args_manager.no_ui:
            yield
        elif self.live:
            self.live.update(Live(self.manager.progress_manager.hash_layout, refresh_per_second=self.manager.config_manager.global_settings_data['UI_Options']['refresh_rate']))
            yield self.live
        else:
            self.live=Live(self.manager.progress_manager.hash_layout, refresh_per_second=self.manager.config_manager.global_settings_data['UI_Options']['refresh_rate'])
            with self.live as live:
                yield live

