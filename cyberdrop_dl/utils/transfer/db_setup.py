from __future__ import annotations

from typing import TYPE_CHECKING

from cyberdrop_dl.utils import constants
from cyberdrop_dl.utils.transfer.transfer_hash_db import transfer_from_old_hash_table

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager

CACHE_FILE = constants.APP_STORAGE / "Cache" / "cache.yaml"
OLD_DB_FILE = constants.APP_STORAGE / "download_history.sqlite"
NEW_DB_FILE = constants.APP_STORAGE / "Cache" / "cyberdrop.db"


class TransitionManager:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager

    def transfer_v5_to_new_hashtable(self):
        """
        transfers from old v5 hash table to new v5 hash table, that supports multiple hash types per file
        """
        if NEW_DB_FILE.exists():
            transfer_from_old_hash_table(NEW_DB_FILE)
