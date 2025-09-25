from datetime import datetime
from pathlib import Path
from typing import cast

import aiosqlite
import pytest

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, ScrapeItem
from cyberdrop_dl.scraper.scrape_mapper import _create_item_from_row

_MOCK_ROW = {
    "referer": "https://drive.google.com/file/d/1F0YBsnQRvrMbK0p9UlnyLu88kqQ0j_F6/edit",
    "download_path": "/cdl/downloads",
    "completed_at": None,
    "created_at": None,
}


@pytest.fixture
def row() -> aiosqlite.Row:
    return cast("aiosqlite.Row", _MOCK_ROW.copy())


@pytest.fixture
def row_with_dates(row) -> aiosqlite.Row:
    row["completed_at"] = datetime.now().isoformat()
    row["created_at"] = datetime(2023, 1, 1, 10, 0, 0).isoformat()
    return row


def test_scrape_item_creation(row: aiosqlite.Row) -> None:
    item = _create_item_from_row(row)
    assert isinstance(item, ScrapeItem)
    assert item.url == AbsoluteHttpURL("https://drive.google.com/file/d/1F0YBsnQRvrMbK0p9UlnyLu88kqQ0j_F6/edit")
    assert item.retry_path == Path("/cdl/downloads")
    assert item.part_of_album is True
    assert item.retry is True
    assert item.completed_at is None
    assert item.created_at is None


def test_item_with_completed_at(row_with_dates) -> None:
    completed_at_str = row_with_dates["completed_at"]
    row_with_dates["created_at"] = None

    item = _create_item_from_row(row_with_dates)
    expected_timestamp = int(datetime.fromisoformat(completed_at_str).timestamp())
    assert item.completed_at == expected_timestamp
    assert item.created_at is None


def test_item_with_created_at(row) -> None:
    now = datetime.now()
    row["created_at"] = now.isoformat()

    item = _create_item_from_row(row)
    assert item.created_at == int(now.timestamp())
    assert item.completed_at is None


def test_item_with_both_dates(row_with_dates) -> None:
    completed_at_str = row_with_dates["completed_at"]
    created_at_str = row_with_dates["created_at"]

    item = _create_item_from_row(row_with_dates)
    expected_completed_timestamp = int(datetime.fromisoformat(completed_at_str).timestamp())
    expected_created_timestamp = int(datetime.fromisoformat(created_at_str).timestamp())
    assert item.completed_at == expected_completed_timestamp
    assert item.created_at == expected_created_timestamp


def test_missing_download_path(row) -> None:
    del row["download_path"]

    with pytest.raises(KeyError, match="download_path"):
        _create_item_from_row(row)


def test_invalid_date_format(row) -> None:
    row["completed_at"] = "invalid date"

    with pytest.raises(ValueError):
        _create_item_from_row(row)
