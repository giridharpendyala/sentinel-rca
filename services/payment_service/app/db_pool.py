import asyncio
import logging
import random
from contextlib import asynccontextmanager

from fastapi import HTTPException


class SimulatedDBPool:
    """In-process stand-in for a JDBC-style connection pool, sized and timed out
    the same way a real one would be, so exhaustion produces realistic symptoms
    (latency spike, WARN/ERROR log pair, saturated active-connection gauge)
    without needing an actual database.
    """

    def __init__(self, logger: logging.Logger, size: int = 100, acquire_timeout_s: float = 2.0):
        self.logger = logger
        self.size = size
        self.acquire_timeout_s = acquire_timeout_s
        self.active = 0
        self._sem = asyncio.Semaphore(size)

    @asynccontextmanager
    async def acquire(self):
        try:
            await asyncio.wait_for(self._sem.acquire(), timeout=self.acquire_timeout_s)
        except asyncio.TimeoutError:
            self.logger.warning("Timeout waiting for database connection")
            self.logger.error("Unable to acquire JDBC connection")
            raise HTTPException(status_code=503, detail="db_pool_exhausted")

        self.active += 1
        try:
            await asyncio.sleep(random.uniform(0.02, 0.05))
            yield
        finally:
            self.active -= 1
            self._sem.release()
