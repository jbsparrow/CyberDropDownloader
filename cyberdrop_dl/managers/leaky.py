from typing import Coroutine
from aiolimiter import AsyncLimiter

MIN_BUCKET_SIZE =1024*1024*64

class LeakyBucket( AsyncLimiter):
    def __init__(self,manager):
        self.download_speed_limit = manager.config_manager.global_settings_data['Rate_Limiting_Options']['download_speed_limit']
        # if self.download_speed_limit==0:
        #     rate=1
        # elif self.download_speed_limit>=MIN_BUCKET_SIZE:
        #     rate=1
        # else:
        #     rate=int(MIN_BUCKET_SIZE/self.download_speed_limit)
        super().__init__(self.download_speed_limit,rate=1)
    async def acquire(self, amount: float = 1):
        if self.download_speed_limit<=0:
            return
        if not isinstance(amount, int):
            amount=len(amount)
        await super().acquire(amount)
