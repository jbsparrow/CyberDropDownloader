from __future__ import annotations

from pathlib import Path
from sqlite3 import IntegrityError
from typing import TYPE_CHECKING

from rich.console import Console

from cyberdrop_dl.utils.database.table_definitions import create_hash

if TYPE_CHECKING:
    import aiosqlite
    from yarl import URL

console = Console()


class HashTable:
    def __init__(self, db_conn: aiosqlite.Connection) -> None:
        self.db_conn: aiosqlite.Connection = db_conn

    async def startup(self) -> None:
        """Startup process for the HistoryTable."""
        await self.db_conn.execute(create_hash)
        await self.add_columns_hash()
        await self.db_conn.commit()

    async def add_columns_hash(self) -> None:
        cursor = await self.db_conn.cursor()
        result = await cursor.execute("""pragma table_info(hash)""")
        result = await result.fetchall()
        current_cols = [col[1] for col in result]

        if "download_filename" not in current_cols:
            await self.db_conn.execute("""ALTER TABLE hash RENAME COLUMN filename TO download_filename;""")
            await self.db_conn.commit()

        if "file_size" not in current_cols:
            await self.db_conn.execute("""ALTER TABLE hash RENAME COLUMN size TO file_size;""")
            await self.db_conn.commit()

        if "original_filename" not in current_cols:
            await self.db_conn.execute("""ALTER TABLE hash ADD COLUMN original_filename TEXT""")
            await self.db_conn.commit()

        if "referer" not in current_cols:
            await self.db_conn.execute("""ALTER TABLE hash ADD COLUMN referer TEXT""")
            await self.db_conn.commit()

    async def get_file_hash_exists(self, full_path: Path | str) -> str | None:
        """Checks if a file exists in the database based on its folder, filename, and size.

        Args:
            full_path: Full path to the file to check.

        Returns:
            hash if  exists
        """
        try:
            # Extract folder, filename, and size from the full path
            path = Path(full_path).absolute()
            folder = str(path.parent)
            filename = path.name
            size = path.stat().st_size

            # Connect to the database
            cursor = await self.db_conn.cursor()

            # Check if the file exists with matching folder, filename, and size
            await cursor.execute(
                "SELECT hash FROM hash WHERE folder=? AND download_filename=? AND file_size=?",
                (folder, filename, size),
            )
            result = await cursor.fetchone()
            if result and result[0]:
                return result[0]
        except Exception as e:
            console.print(f"Error checking file: {e}")
        return None

    async def get_files_with_hash_matches(self, hash_value: str, size: int) -> list:
        """Retrieves a list of (folder, filename) tuples based on a given hash.

        Args:
            hash_value: The hash value to search for.
            size: file size

        Returns:
            A list of (folder, filename) tuples, or an empty list if no matches found.
        """
        cursor = await self.db_conn.cursor()

        try:
            await cursor.execute(
                "SELECT folder, download_filename FROM hash WHERE hash = ? and file_size=?",
                (hash_value, size),
            )
            return await cursor.fetchall()
        except Exception as e:
            console.print(f"Error retrieving folder and filename: {e}")
            return []

    async def insert_or_update_hash_db(self, hash_value: str, file: str, original_filename: str, referer: URL) -> bool:
        """Inserts or updates a record in the specified SQLite database.

        Args:
            hash_value: The calculated hash of the file.
            file: The file path
            original_filename: The name original name of the file.
            referer: referer URL

        Returns:
            True if the record was inserted or updated successfully, False otherwise.
        """
        referer = str(referer)
        cursor = await self.db_conn.cursor()
        full_path = Path(file).absolute()
        file_size = full_path.stat().st_size

        download_filename = full_path.name
        original_filename = referer or download_filename
        folder = str(full_path.parent)

        # Assuming a table named 'file_info' with columns: id (primary key), hash, size, filename, folder
        try:
            await cursor.execute(
                "INSERT INTO hash (hash, file_size, download_filename, folder,original_filename,referer) VALUES (?, ?, ?, ?,?,?)",
                (hash_value, file_size, download_filename, folder, original_filename, referer),
            )
            await self.db_conn.commit()
        except IntegrityError as _:
            # Handle potential duplicate key (assuming a unique constraint on hash, filename, and folder)
            await cursor.execute(
                """UPDATE hash
    SET file_size = ?,
    hash = ?,
    referer= CASE WHEN ? IS NOT NULL THEN ? ELSE referer END,
    original_filename = CASE WHEN ? IS NOT NULL THEN ? ELSE original_filename END
WHERE download_filename = ? AND folder = ?;""",
                (
                    file_size,
                    hash_value,
                    referer,
                    referer,
                    original_filename,
                    original_filename,
                    download_filename,
                    folder,
                ),
            )
            await self.db_conn.commit()
        except Exception as e:
            console.print(f"Error inserting/updating record: {e}")
            return False
        return True

    async def get_all_unique_hashes(self) -> list:
        """Retrieves a list of (folder, filename) tuples based on a given hash.

        Args:
            hash_value: The hash value to search for.

        Returns:
            A list of (folder, filename) tuples, or an empty list if no matches found.
        """
        cursor = await self.db_conn.cursor()

        try:
            await cursor.execute("SELECT DISTINCT hash FROM hash")
            results = await cursor.fetchall()
            return [x[0] for x in results]
        except Exception as e:
            console.print(f"Error retrieving folder and filename: {e}")
            return []
