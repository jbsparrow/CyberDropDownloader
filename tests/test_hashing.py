from __future__ import annotations

import sqlite3
from collections import Counter
from typing import TYPE_CHECKING

import pytest

from cyberdrop_dl.clients.hash_client import hash_directory_scanner

if TYPE_CHECKING:
    from pathlib import Path

    from cyberdrop_dl.managers.manager import Manager


def get_hashes(path: Path) -> set[tuple[str, str]]:
    query = "SELECT hash_type, hash FROM hash "
    conn = sqlite3.connect(path)
    try:
        cursor = conn.execute(query)
        return set(cursor.fetchall())
    finally:
        conn.close()


def create_files(path: Path, number: int) -> None:
    for i in range(number):
        file = path / f"file_{i}"
        file.write_text(str(i), encoding="utf-8")


@pytest.mark.parametrize(
    "expected_results",
    [
        {
            ("xxh128", "cb358fcee0dfde56fb95a7322f5da314"),
            ("xxh128", "df3ce784d856334d65cd25028f98f158"),
            ("xxh128", "ce8f15881282a4001982e3a7bb241055"),
        },
        {
            ("xxh128", "ce8f15881282a4001982e3a7bb241055"),
            ("md5", "cfcd208495d565ef66e7dff9f98764da"),
        },
        {
            ("xxh128", "ce8f15881282a4001982e3a7bb241055"),
            ("md5", "cfcd208495d565ef66e7dff9f98764da"),
            ("sha256", "5feceb66ffc86f38d952786c6d696c79c2dbc239dd4e91b46729d73a27fb57e9"),
        },
    ],
)
def test_hash_directory_scanner(manager: Manager, expected_results: set[tuple[str, str]]) -> None:
    count = Counter(x[0] for x in expected_results)
    n_files = max(count.values())
    algos = count.keys()
    assert len(expected_results) == len(algos) * n_files
    manager.config.dupe_cleanup_options.add_md5_hash = "md5" in algos
    manager.config.dupe_cleanup_options.add_sha256_hash = "sha256" in algos

    manager.path_manager.download_folder.mkdir(parents=True)
    db_path = manager.path_manager.history_db
    hash_directory_scanner(manager, manager.path_manager.download_folder)
    assert not get_hashes(db_path)
    create_files(manager.path_manager.download_folder, n_files)
    hash_directory_scanner(manager, manager.path_manager.download_folder)
    results = get_hashes(db_path)
    assert len(results) == len(expected_results)
    assert results == expected_results
