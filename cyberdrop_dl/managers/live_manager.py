from rich.live import Live
from contextlib import contextmanager



class LiveManager:
    def __init__(self,manager):
        self.manager = manager
        self.live=Live(auto_refresh=True, refresh_per_second=self.manager.config_manager.global_settings_data['UI_Options']['refresh_rate'])
    @contextmanager
    def get_main_live(self,stop=False):
        try:
            if self.manager.args_manager.no_ui:
                yield  
            else:
                self.live.start()
                self.live.update(self.manager.progress_manager.layout,refresh=True)
                yield  self.live
            if stop:
                self.live.stop()
        except Exception as e:
            print(e)
                

            
            

                
    @contextmanager
    def get_remove_file_via_hash_live(self,stop=False):
        try:
            if self.manager.args_manager.no_ui:
                yield  
            else:
                self.live.start()
                self.live.update(self.manager.progress_manager.hash_remove_layout,refresh=True)
                yield
            if stop:
                self.live.stop()
        except Exception as e:
            print(e)
                



    @contextmanager
    def get_hash_live(self,stop=False):
        try:
            if self.manager.args_manager.no_ui:
                yield  
            else:
                self.live.start()
                self.live.update(self.manager.progress_manager.hash_layout,refresh=True)
                yield
            if stop:
                self.live.stop()
        except Exception as e:
            print(e)
                
