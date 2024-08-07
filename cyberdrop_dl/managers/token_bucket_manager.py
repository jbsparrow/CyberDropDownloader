import time
import asyncio
class TokenBucket:
    def __init__(self, capacity, fill_rate):
        self.capacity = capacity
        self.fill_rate = fill_rate
        self.tokens = 0
        self.last_update = time.time()
        self._lock=asyncio.Lock()

    async def consume(self, tokens):
        if self.capacity<=0:
            return True
        while True:
            async with self._lock:
                now = time.time()
                delta = now - self.last_update
                self.last_update = now
                self.tokens = min(self.capacity, self.tokens + delta * self.fill_rate)

                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True

            # Not enough tokens, wait for refill
            await asyncio.sleep(0.01)