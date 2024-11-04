from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import aiofiles

from cyberdrop_dl.utils.utilities import log, log_spacer

if TYPE_CHECKING:
    from yarl import URL
    from cyberdrop_dl.managers.manager import Manager

CSV_DELIMITER = ','


class LogManager:
    def __init__(self, manager: 'Manager'):
        self.manager = manager
        self.main_log: Path = manager.path_manager.main_log
        self.last_post_log: Path = manager.path_manager.last_post_log
        self.unsupported_urls_log: Path = manager.path_manager.unsupported_urls_log
        self.download_error_log: Path = manager.path_manager.download_error_log
        self.scrape_error_log: Path = manager.path_manager.scrape_error_log

    def startup(self) -> None:
        """Startup process for the file manager"""
        for var in vars(self).values():
            if isinstance(var, Path):
                var.unlink(missing_ok=True)

    @staticmethod
    async def write_to_csv(file: Path, **kwargs):
        "Write to the specified csv file. kwargs are columns for the CSV "
        # padding of 1 to the left
        row = {key: f"{value} " for key, value in kwargs.items()}
        write_headers = not file.is_file()
        async with aiofiles.open(file, 'a', encoding="utf8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=row.keys(), delimiter=CSV_DELIMITER, quoting=csv.QUOTE_MINIMAL)
            if write_headers:
                await writer.writeheader()
            await writer.writerow(row)

    async def write_last_post_log(self, url: URL) -> None:
        """Writes to the last post log"""
        await self.write_to_csv(self.last_post_log, url=url)

    async def write_unsupported_urls_log(self, url: URL, origin: Optional[URL] = None) -> None:
        """Writes to the unsupported urls log"""
        await self.write_to_csv(self.unsupported_urls_log, url=url, origin=origin)

    async def write_download_error_log(self, url: URL, error_message: str, origin: Optional[URL] = None) -> None:
        """Writes to the download error log"""
        await self.write_to_csv(self.download_error_log, url=url, error=error_message, origin=origin)

    async def write_scrape_error_log(self, url: URL, error_message: str, origin: Optional[URL] = None) -> None:
        """Writes to the scrape error log"""
        await self.write_to_csv(self.scrape_error_log, url=url, error=error_message, origin=origin)

    async def update_last_forum_post(self) -> None:
        """Updates the last forum post"""

        input_file = self.manager.path_manager.input_file
        if not input_file.is_file() or not self.last_post_log.is_file():
            return

        await log_spacer(20)
        await log("Updating Last Forum Posts...\n", 20)

        current_urls, current_base_urls, new_urls, new_base_urls = [], [], [], []

        async with aiofiles.open(input_file, 'r', encoding="utf8") as f:
            async for line in f:
                url = base_url = line.strip().removesuffix('/')

                if "https" in url and "/post-" in url:
                    base_url = url.rsplit("/post", 1)[0]

                # only keep 1 url of the same thread
                if base_url not in current_base_urls:
                    current_urls.append(url)
                    current_base_urls.append(base_url)

        async with aiofiles.open(self.last_post_log, 'r', encoding="utf8") as f:
            reader = csv.DictReader(await f.readlines())
            for row in reader:
                new_url = base_url = row.get("url").strip().removesuffix('/')

                if "https" in new_url and "/post-" in new_url:
                    base_url = new_url.rsplit("/post", 1)[0]

                # only keep 1 url of the same thread
                if base_url not in new_base_urls:
                    new_urls.append(new_url)
                    new_base_urls.append(base_url)

        updated_urls = current_urls.copy()
        for new_url, base in zip(new_urls, new_base_urls):
            if base in current_base_urls:
                index = current_base_urls.index(base)
                old_url = current_urls[index]
                if old_url == new_url:
                    continue
                await log(f"Updating {base}\n  {old_url = }\n  {new_url = }", 20)
                updated_urls[index] = new_url

        if updated_urls == current_urls:
            await log("No URLs updated", 20)
            return

        async with aiofiles.open(input_file, 'w', encoding="utf8") as f:
            await f.write("\n".join(updated_urls))
