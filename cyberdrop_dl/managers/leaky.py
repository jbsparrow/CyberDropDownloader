from aiolimiter import AsyncLimiter

class LeakyBucket( AsyncLimiter):
    def __init__(self,manager):
        self.download_speed_limit = manager.config_manager.global_settings_data['Rate_Limiting_Options']['download_speed_limit']
        super().__init__(self.download_speed_limit*1024,1)
    async def acquire(self, amount: float = 1):
        if self.download_speed_limit<=0:
            return
        if not isinstance(amount, int):
            amount=len(amount)
        await super().acquire(amount)
