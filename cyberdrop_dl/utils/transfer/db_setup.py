from __future__ import annotations

from typing import TYPE_CHECKING

from cyberdrop_dl.utils import constants
from cyberdrop_dl.utils.transfer.transfer_hash_db import transfer_from_old_hash_table

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class TransitionManager:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager

    def transfer_v5_to_new_hashtable(self):
        """
        transfers from old v5 hash table to new v5 hash table, that supports multiple hash types per file
        """
        db_path = constants.APP_STORAGE / "Cache" / "cyberdrop.db"
        if db_path.exists():
            transfer_from_old_hash_table(db_path)
