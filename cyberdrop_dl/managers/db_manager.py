from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import field
from typing import TYPE_CHECKING

import aiosqlite

from cyberdrop_dl.utils.database.tables.hash_table import HashTable
from cyberdrop_dl.utils.database.tables.history_table import HistoryTable
from cyberdrop_dl.utils.database.tables.temp_referer_table import TempRefererTable

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

    from cyberdrop_dl.managers.manager import Manager


class DBConnectionPool:
    """Connection pool for SQLite database operations with read/write optimization."""

    def __init__(self, db_path: Path, pool_size: int = 5) -> None:
        self._db_path = db_path
        self._pool_size = pool_size
        self._read_pool: list[aiosqlite.Connection] = []
        self._write_pool: list[aiosqlite.Connection] = []
        self._read_semaphore = asyncio.Semaphore(pool_size)
        self._write_semaphore = asyncio.Semaphore(2)  # Limit writes for SQLite
        self._pool_lock = asyncio.Lock()
        self._initialized = False

    async def _create_connection(self) -> aiosqlite.Connection:
        """Create a new database connection with optimized settings."""
        conn = await aiosqlite.connect(self._db_path)
        
        # Optimize SQLite settings for concurrent access
        await conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
        await conn.execute("PRAGMA synchronous=NORMAL")  # Balance safety/performance
        await conn.execute("PRAGMA cache_size=10000")  # Increase cache
        await conn.execute("PRAGMA temp_store=memory")  # Use memory for temp tables
        await conn.execute("PRAGMA mmap_size=268435456")  # 256MB memory mapped I/O
        
        return conn

    async def initialize(self) -> None:
        """Initialize the connection pool."""
        async with self._pool_lock:
            if self._initialized:
                return
                
            # Create read connections
            for _ in range(self._pool_size):
                conn = await self._create_connection()
                self._read_pool.append(conn)
                
            # Create write connections
            for _ in range(2):  # SQLite handles writes better with fewer connections
                conn = await self._create_connection()
                self._write_pool.append(conn)
                
            self._initialized = True

    @asynccontextmanager
    async def get_read_connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Get a connection optimized for read operations."""
        async with self._read_semaphore:
            async with self._pool_lock:
                if not self._read_pool:
                    # Create new connection if pool is empty
                    conn = await self._create_connection()
                else:
                    conn = self._read_pool.pop()
                    
            try:
                yield conn
            finally:
                async with self._pool_lock:
                    self._read_pool.append(conn)

    @asynccontextmanager
    async def get_write_connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Get a connection optimized for write operations."""
        async with self._write_semaphore:
            async with self._pool_lock:
                if not self._write_pool:
                    # Create new connection if pool is empty
                    conn = await self._create_connection()
                else:
                    conn = self._write_pool.pop()
                    
            try:
                yield conn
            finally:
                async with self._pool_lock:
                    self._write_pool.append(conn)

    async def close(self) -> None:
        """Close all connections in the pool."""
        async with self._pool_lock:
            # Close read connections
            for conn in self._read_pool:
                await conn.close()
            self._read_pool.clear()
            
            # Close write connections
            for conn in self._write_pool:
                await conn.close()
            self._write_pool.clear()
            
            self._initialized = False

    def get_stats(self) -> dict[str, int]:
        """Get connection pool statistics."""
        return {
            "read_pool_size": len(self._read_pool),
            "write_pool_size": len(self._write_pool),
            "max_read_connections": self._pool_size,
            "max_write_connections": 2,
            "initialized": self._initialized
        }


class DBManager:
    def __init__(self, manager: Manager, db_path: Path) -> None:
        self.manager = manager
        self._db_path: Path = db_path
        self._db_conn: aiosqlite.Connection = field(init=False)
        self._connection_pool: DBConnectionPool = field(init=False)

        self.ignore_history: bool = False

        self.history_table: HistoryTable = field(init=False)
        self.hash_table: HashTable = field(init=False)
        self.temp_referer_table: TempRefererTable = field(init=False)

    async def startup(self) -> None:
        """Startup process for the DBManager."""
        # Initialize both single connection (for compatibility) and connection pool
        self._db_conn = await aiosqlite.connect(self._db_path)
        self._connection_pool = DBConnectionPool(self._db_path, pool_size=5)
        await self._connection_pool.initialize()

        self.ignore_history = self.manager.config_manager.settings_data.runtime_options.ignore_history

        # Create table instances with single connection for compatibility
        self.history_table = HistoryTable(self._db_conn)
        self.hash_table = HashTable(self._db_conn)
        self.temp_referer_table = TempRefererTable(self._db_conn)

        self.history_table.ignore_history = self.ignore_history
        self.temp_referer_table.ignore_history = self.ignore_history

        await self._pre_allocate()

        await self.history_table.startup()
        await self.hash_table.startup()
        await self.temp_referer_table.startup()
        await self.run_fixes()

    async def run_fixes(self):
        if not self.manager.cache_manager.get("fixed_empty_download_filenames"):
            await self.history_table.delete_invalid_rows()
            self.manager.cache_manager.save("fixed_empty_download_filenames", True)

    async def close(self) -> None:
        """Close the DBManager."""
        await self.temp_referer_table.sql_drop_temp_referers()
        await self._db_conn.close()
        await self._connection_pool.close()

    async def _pre_allocate(self) -> None:
        """We pre-allocate 100MB of space to the SQL file just in case the user runs out of disk space."""
        create_pre_allocation_table = "CREATE TABLE IF NOT EXISTS t(x);"
        drop_pre_allocation_table = "DROP TABLE t;"

        fill_pre_allocation = "INSERT INTO t VALUES(zeroblob(100*1024*1024));"  # 100 mb
        check_pre_allocation = "PRAGMA freelist_count;"

        async with self._connection_pool.get_write_connection() as conn:
            result = await conn.execute(check_pre_allocation)
            free_space = await result.fetchone()

            if free_space and free_space[0] <= 1024:
                await conn.execute(create_pre_allocation_table)
                await conn.commit()
                await conn.execute(fill_pre_allocation)
                await conn.commit()
                await conn.execute(drop_pre_allocation_table)
                await conn.commit()

    def get_pool_stats(self) -> dict[str, int]:
        """Get database connection pool statistics."""
        return self._connection_pool.get_stats()

    async def execute_read_query(self, query: str, params: tuple = ()) -> list:
        """Execute a read query using connection pool for better performance."""
        async with self._connection_pool.get_read_connection() as conn:
            cursor = await conn.cursor()
            await cursor.execute(query, params)
            return await cursor.fetchall()

    async def execute_write_query(self, query: str, params: tuple = ()) -> None:
        """Execute a write query using connection pool for better performance."""
        async with self._connection_pool.get_write_connection() as conn:
            cursor = await conn.cursor()
            await cursor.execute(query, params)
            await conn.commit()

    async def execute_batch_writes(self, queries: list[tuple[str, tuple]]) -> None:
        """Execute multiple write queries in a single transaction for better performance."""
        async with self._connection_pool.get_write_connection() as conn:
            cursor = await conn.cursor()
            try:
                await conn.execute("BEGIN TRANSACTION")
                for query, params in queries:
                    await cursor.execute(query, params)
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
