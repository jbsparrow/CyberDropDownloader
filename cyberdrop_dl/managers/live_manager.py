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
            self.prev_live=self.live
            new_live=Live(self.manager.progress_manager.layout, refresh_per_second=self.manager.config_manager.global_settings_data['UI_Options']['refresh_rate'])
            self.live.update(new_live)
            yield self.live
            self.live.update(self.prev_live)
        else:
            self.live=Live(self.manager.progress_manager.layout, refresh_per_second=self.manager.config_manager.global_settings_data['UI_Options']['refresh_rate'])
            self.live.start()
            yield self.live
            self.live.stop()
            self.live=None

            
    @contextmanager
    def get_hash_remove_live(self):
        if self.manager.args_manager.no_ui:
            yield
        elif self.live:
            self.prev_live=self.live
            new_live=Live(self.manager.progress_manager.hash_remove_layout, refresh_per_second=self.manager.config_manager.global_settings_data['UI_Options']['refresh_rate'])
            self.live.update(new_live)
            yield self.live
            self.live.update(self.prev_live)
        else:
            self.live=Live(self.manager.progress_manager.hash_remove_layout, refresh_per_second=self.manager.config_manager.global_settings_data['UI_Options']['refresh_rate'])
            self.live.start()
            yield self.live
            self.live.stop()
            self.live=None



    @contextmanager
    def get_hash_live(self):
        if self.manager.args_manager.no_ui:
            yield
        elif self.live:
            self.prev_live=self.live
            self.live.update(Live(self.manager.progress_manager.hash_layout, refresh_per_second=self.manager.config_manager.global_settings_data['UI_Options']['refresh_rate']))
            yield
            self.live.update(self.prev_live)
        else:
            self.live=Live(self.manager.progress_manager.hash_layout, refresh_per_second=self.manager.config_manager.global_settings_data['UI_Options']['refresh_rate'])
            self.live.start()
            yield self.live
            self.live.stop()
            self.live=None