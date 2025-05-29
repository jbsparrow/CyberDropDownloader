from __future__ import annotations

import asyncio
import csv
from asyncio import Lock
from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles

from cyberdrop_dl import config
from cyberdrop_dl.constants import CSV_DELIMITER
from cyberdrop_dl.exceptions import get_origin
from cyberdrop_dl.utils.logger import log, log_spacer

if TYPE_CHECKING:
    from yarl import URL

    from cyberdrop_dl.data_structures.url_objects import MediaItem
    from cyberdrop_dl.managers.manager import Manager


class LogManager:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self._csv_locks = {}

    def startup(self) -> None:
        """Startup process for the file manager."""

        for var in vars(config.settings.logs).values():
            if isinstance(var, Path) and var.suffix in (".csv", ".log"):
                var.unlink(missing_ok=True)

    async def write_to_csv(self, file: Path, **kwargs) -> None:
        """Write to the specified csv file. kwargs are columns for the CSV."""
        self._csv_locks[file] = self._csv_locks.get(file, Lock())
        async with self._csv_locks[file]:
            write_headers = not await asyncio.to_thread(file.is_file)
            async with aiofiles.open(file, "a", encoding="utf8", newline="") as csv_file:
                writer = csv.DictWriter(
                    csv_file, fieldnames=kwargs.keys(), delimiter=CSV_DELIMITER, quoting=csv.QUOTE_ALL
                )
                if write_headers:
                    await writer.writeheader()
                await writer.writerow(kwargs)

    async def write_last_post_log(self, url: URL) -> None:
        """Writes to the last post log."""
        await self.write_to_csv(config.settings.logs.last_forum_post, url=url)

    async def write_unsupported_urls_log(self, url: URL, origin: URL | None = None) -> None:
        """Writes to the unsupported urls log."""
        await self.write_to_csv(config.settings.logs.unsupported_urls, url=url, origin=origin)

    async def write_download_error_log(self, media_item: MediaItem, error_message: str) -> None:
        """Writes to the download error log."""
        origin = get_origin(media_item)
        await self.write_to_csv(
            config.settings.logs.download_error_urls,
            url=media_item.url,
            error=error_message,
            referer=media_item.referer,
            origin=origin,
        )

    async def write_scrape_error_log(
        self, url: URL | str, error_message: str, origin: URL | Path | None = None
    ) -> None:
        """Writes to the scrape error log."""
        await self.write_to_csv(config.settings.logs.scrape_error_urls, url=url, error=error_message, origin=origin)

    async def write_dedupe_log(self, og_file: Path, hash: str, removed_file: Path) -> None:
        """Writes to the dedupe log."""
        await self.write_to_csv(
            config.settings.logs.dedupe_log, original_file=og_file, hash=hash, removed_file=removed_file
        )

    async def update_last_forum_post(self) -> None:
        """Updates the last forum post."""

        def proceed() -> bool:
            return config.settings.files.input_file.is_file() and config.settings.logs.last_forum_post.is_file()

        if not await asyncio.to_thread(proceed):
            return

        log_spacer(20)
        log("Updating Last Forum Posts...\n", 20)

        current_urls, current_base_urls, new_urls, new_base_urls = [], [], [], []
        try:
            async with aiofiles.open(config.settings.files.input_file, encoding="utf8") as f:
                async for line in f:
                    url = base_url = line.strip().removesuffix("/")

                    if "https" in url and "/post-" in url:
                        base_url = url.rsplit("/post", 1)[0]

                    # only keep 1 url of the same thread
                    if base_url not in current_base_urls:
                        current_urls.append(url)
                        current_base_urls.append(base_url)
        except UnicodeDecodeError:
            log("Unable to read input file, skipping update_last_forum_post", 40)
            return

        async with aiofiles.open(config.settings.logs.last_forum_post, encoding="utf8") as f:
            reader = csv.DictReader(await f.readlines())
            for row in reader:
                new_url = base_url = row.get("url").strip().removesuffix("/")  # type: ignore

                if "https" in new_url and "/post-" in new_url:
                    base_url = new_url.rsplit("/post", 1)[0]

                # only keep 1 url of the same thread
                if base_url not in new_base_urls:
                    new_urls.append(new_url)
                    new_base_urls.append(base_url)

        updated_urls = current_urls.copy()
        for new_url, base in zip(new_urls, new_base_urls, strict=False):
            if base in current_base_urls:
                index = current_base_urls.index(base)
                old_url = current_urls[index]
                if old_url == new_url:
                    continue
                log(f"Updating {base}\n  {old_url = }\n  {new_url = }", 20)
                updated_urls[index] = new_url

        if updated_urls == current_urls:
            log("No URLs updated", 20)
            return

        async with aiofiles.open(config.settings.files.input_file, "w", encoding="utf8") as f:
            await f.write("\n".join(updated_urls))
