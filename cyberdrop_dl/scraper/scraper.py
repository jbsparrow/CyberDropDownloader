from __future__ import annotations

import re
from dataclasses import Field
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles
import arrow
from yarl import URL

from cyberdrop_dl.clients.errors import JDownloaderError
from cyberdrop_dl.downloader.downloader import Downloader
from cyberdrop_dl.scraper import CRAWLERS
from cyberdrop_dl.scraper.filters import (
    has_valid_extension,
    is_in_domain_list,
    is_outside_date_range,
    is_valid_url,
    remove_trailing_slash,
)
from cyberdrop_dl.scraper.jdownloader import JDownloader
from cyberdrop_dl.utils.constants import BLOCKED_DOMAINS, REGEX_LINKS
from cyberdrop_dl.utils.data_enums_classes.url_objects import MediaItem, ScrapeItem
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import get_download_path, get_filename_and_ext

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.scraper.crawler import Crawler


class ScrapeMapper:
    """This class maps links to their respective handlers, or JDownloader if they are unsupported."""

    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.existing_crawlers: dict[str, Crawler] = {}
        self.no_crawler_downloader = Downloader(self.manager, "no_crawler")
        self.jdownloader = JDownloader(self.manager)
        self.jdownloader_whitelist = self.manager.config_manager.settings_data.runtime_options.jdownloader_whitelist
        self.count = 0

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    def start_scrapers(self) -> None:
        """Starts all scrapers."""
        for crawler in CRAWLERS:
            if not crawler.SUPPORTED_SITES:
                site_crawler = crawler(self.manager)
                self.existing_crawlers[site_crawler.domain] = site_crawler
                continue

            for site, domains in crawler.SUPPORTED_SITES.items():
                site_crawler = crawler(self.manager, site)
                for domain in domains:
                    self.existing_crawlers[domain] = site_crawler

    def start_jdownloader(self) -> None:
        """Starts JDownloader."""
        if self.jdownloader.enabled and isinstance(self.jdownloader.jdownloader_agent, Field):
            self.jdownloader.jdownloader_setup()

    def start_real_debrid(self) -> None:
        """Starts RealDebrid."""
        if isinstance(self.manager.real_debrid_manager.api, Field):
            self.manager.real_debrid_manager.startup()

        if self.manager.real_debrid_manager.enabled:
            from cyberdrop_dl.scraper.crawlers.realdebrid_crawler import RealDebridCrawler

            self.existing_crawlers["real-debrid"] = RealDebridCrawler(self.manager)
            self.existing_crawlers["real-debrid"].startup()

    async def start(self) -> None:
        """Starts the orchestra."""
        self.manager.scrape_mapper = self
        self.manager.client_manager.load_cookie_files()
        self.start_scrapers()
        self.start_jdownloader()
        self.start_real_debrid()
        self.no_crawler_downloader.startup()

        if self.manager.parsed_args.cli_only_args.retry_failed:
            await self.load_failed_links()
        elif self.manager.parsed_args.cli_only_args.retry_all:
            await self.load_all_links()
        elif self.manager.parsed_args.cli_only_args.retry_maintenance:
            await self.load_all_bunkr_failed_links_via_hash()
        else:
            await self.load_links()

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def regex_links(line: str) -> list:
        """Regex grab the links from the URLs.txt file.

        This allows code blocks or full paragraphs to be copy and pasted into the URLs.txt.
        """
        yarl_links = []
        if line.lstrip().rstrip().startswith("#"):
            return yarl_links

        all_links = [x.group().replace(".md.", ".") for x in re.finditer(REGEX_LINKS, line)]
        for link in all_links:
            encoded = "%" in link
            yarl_links.append(URL(link, encoded=encoded))
        return yarl_links

    async def parse_input_file_groups(self) -> dict[str, URL]:
        """Split URLs from input file by their groups."""
        input_file = self.manager.path_manager.input_file
        links = {"": []}
        block_quote = False
        thread_title = ""
        async with aiofiles.open(input_file, encoding="utf8") as f:
            async for line in f:
                assert isinstance(line, str)

                if line.startswith(("---", "===")):
                    thread_title = line.replace("---", "").replace("===", "").strip()
                    if thread_title and thread_title not in links:
                        links[thread_title] = []

                if thread_title:
                    links[thread_title].extend(self.regex_links(line))
                else:
                    block_quote = not block_quote if line == "#\n" else block_quote
                    if not block_quote:
                        links[""].extend(self.regex_links(line))
        return links

    async def load_links(self) -> None:
        """Loads links from args / input file."""
        input_file = self.manager.path_manager.input_file
        # we need to touch the file just in case, purge_tree deletes it
        if not input_file.is_file():
            input_file.touch(exist_ok=True)

        links = {"": []}
        if not self.manager.parsed_args.cli_only_args.links:
            links = await self.parse_input_file_groups()

        else:
            links[""].extend(self.manager.parsed_args.cli_only_args.links)

        links = {k: list(filter(None, v)) for k, v in links.items()}
        items = []

        if not links:
            log("No valid links found.", 30)
        for title in links:
            for url in links[title]:
                item = self.create_item_from_link(url)
                if title:
                    item.add_to_parent_title(title)
                    item.part_of_album = True
                if self.filter_items(item):
                    items.append(item)
        for item in items:
            self.manager.task_group.create_task(self.send_to_crawler(item))

    async def load_failed_links(self) -> None:
        """Loads failed links from database."""
        entries = await self.manager.db_manager.history_table.get_failed_items()
        items = []
        for entry in entries:
            item = self.create_item_from_entry(entry)
            if self.filter_items(item):
                items.append(item)
        if self.manager.parsed_args.cli_only_args.max_items_retry:
            items = items[: self.manager.parsed_args.cli_only_args.max_items_retry]
        for item in items:
            self.manager.task_group.create_task(self.send_to_crawler(item))

    async def load_all_links(self) -> None:
        """Loads all links from database."""
        after = self.manager.parsed_args.cli_only_args.completed_after or date.fromtimestamp(0)

        before = self.manager.parsed_args.cli_only_args.completed_before or datetime.now().date()
        entries = await self.manager.db_manager.history_table.get_all_items(
            after,
            before,
        )
        items = []
        for entry in entries:
            item = self.create_item_from_entry(entry)
            if self.filter_items(item):
                items.append(item)
        if self.manager.parsed_args.cli_only_args.max_items_retry:
            items = items[: self.manager.parsed_args.cli_only_args.max_items_retry]
        for item in items:
            self.manager.task_group.create_task(self.send_to_crawler(item))

    async def load_all_bunkr_failed_links_via_hash(self) -> None:
        """Loads all bunkr links with maintenance hash."""
        entries = await self.manager.db_manager.history_table.get_all_bunkr_failed()
        entries = sorted(set(entries), reverse=True, key=lambda x: arrow.get(x[-1]))
        items = []
        for entry in entries:
            item = self.create_item_from_entry(entry)
            if self.filter_items(item):
                items.append(item)
        if self.manager.parsed_args.cli_only_args.max_items_retry:
            items = items[: self.manager.parsed_args.cli_only_args.max_items_retry]
        for item in items:
            self.manager.task_group.create_task(self.send_to_crawler(item))

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def filter_and_send_to_crawler(self, scrape_item: ScrapeItem) -> None:
        """Send scrape_item to a supported crawler."""
        if not isinstance(scrape_item.url, URL):
            scrape_item.url = URL(scrape_item.url)
        if self.filter_items(scrape_item):
            await self.send_to_crawler(scrape_item)

    @staticmethod
    def create_item_from_link(link: URL) -> ScrapeItem:
        item = ScrapeItem(url=link)
        return item

    @staticmethod
    def create_item_from_entry(entry: list) -> ScrapeItem:
        url = URL(entry[0])
        retry_path = Path(entry[1])
        scrape_item = ScrapeItem(url=url, part_of_album=True, retry=True, retry_path=retry_path)
        completed_at = entry[2]
        created_at = entry[3]
        if not isinstance(scrape_item.url, URL):
            scrape_item.url = URL(scrape_item.url)
        scrape_item.completed_at = completed_at
        scrape_item.created_at = created_at
        return scrape_item

    async def send_to_crawler(self, scrape_item: ScrapeItem) -> None:
        """Maps URLs to their respective handlers."""
        scrape_item.url = remove_trailing_slash(scrape_item.url)
        supported_domain = [key for key in self.existing_crawlers if key in scrape_item.url.host]
        jdownloader_whitelisted = True
        if self.jdownloader_whitelist:
            jdownloader_whitelisted = any(domain in scrape_item.url.host for domain in self.jdownloader_whitelist)

        if supported_domain:
            # get most restrictive domain if multiple domain matches
            supported_domain = max(supported_domain, key=len)
            scraper = self.existing_crawlers[supported_domain]
            if isinstance(scraper.client, Field):
                scraper.startup()
            self.manager.task_group.create_task(scraper.run(scrape_item))
            return

        if self.manager.real_debrid_manager.enabled and self.manager.real_debrid_manager.is_supported(
            scrape_item.url,
        ):
            log(f"Using RealDebrid for unsupported URL: {scrape_item.url}", 10)
            self.manager.task_group.create_task(self.existing_crawlers["real-debrid"].run(scrape_item))
            return

        if has_valid_extension(scrape_item.url):
            if await self.skip_no_crawler_by_config(scrape_item):
                return

            scrape_item.add_to_parent_title("Loose Files")
            scrape_item.part_of_album = True
            download_folder = get_download_path(self.manager, scrape_item, "no_crawler")
            filename, _ = get_filename_and_ext(scrape_item.url.name)
            media_item = MediaItem(scrape_item.url, scrape_item, download_folder, filename)
            self.manager.task_group.create_task(self.no_crawler_downloader.run(media_item))
            return

        if self.jdownloader.enabled and jdownloader_whitelisted:
            log(f"Sending unsupported URL to JDownloader: {scrape_item.url}", 10)
            success = False
            try:
                download_folder = get_download_path(self.manager, scrape_item, "jdownloader")
                relative_download_dir = download_folder.relative_to(self.manager.path_manager.download_folder)
                self.jdownloader.direct_unsupported_to_jdownloader(
                    scrape_item.url,
                    scrape_item.parent_title,
                    relative_download_dir,
                )
                success = True
            except JDownloaderError as e:
                log(f"Failed to send {scrape_item.url} to JDownloader\n{e.message}", 40)
                await self.manager.log_manager.write_unsupported_urls_log(
                    scrape_item.url,
                    scrape_item.parents[0] if scrape_item.parents else None,
                )
            self.manager.progress_manager.scrape_stats_progress.add_unsupported(sent_to_jdownloader=success)
            return

        log(f"Unsupported URL: {scrape_item.url}", 30)
        await self.manager.log_manager.write_unsupported_urls_log(
            scrape_item.url,
            scrape_item.parents[0] if scrape_item.parents else None,
        )
        self.manager.progress_manager.scrape_stats_progress.add_unsupported()

    def filter_items(self, scrape_item: ScrapeItem) -> bool:
        """Pre-filter scrape items base on URL."""
        if not is_valid_url(scrape_item):
            return False

        if is_in_domain_list(scrape_item, BLOCKED_DOMAINS):
            log(f"Skipping {scrape_item.url} as it is a blocked domain", 10)
            return False

        before = self.manager.parsed_args.cli_only_args.completed_before
        after = self.manager.parsed_args.cli_only_args.completed_after
        if is_outside_date_range(scrape_item, before, after):
            log(f"Skipping {scrape_item.url} as it is outside of the desired date range", 10)
            return False

        skip_hosts = self.manager.config_manager.settings_data.ignore_options.skip_hosts
        if skip_hosts and is_in_domain_list(scrape_item, skip_hosts):
            log(f"Skipping URL by skip_hosts config: {scrape_item.url}", 10)
            return False

        only_hosts = self.manager.config_manager.settings_data.ignore_options.only_hosts
        if only_hosts and not is_in_domain_list(scrape_item, only_hosts):
            log(f"Skipping URL by only_hosts config: {scrape_item.url}", 10)
            return False

        return True

    async def skip_no_crawler_by_config(self, scrape_item: ScrapeItem) -> bool:
        check_complete = await self.manager.db_manager.history_table.check_complete(
            "no_crawler",
            scrape_item.url,
            scrape_item.url,
        )
        if check_complete:
            log(f"Skipping {scrape_item.url} as it has already been downloaded", 10)
            self.manager.progress_manager.download_progress.add_previously_completed()
            return True

        posible_referer = scrape_item.parents[-1] if scrape_item.parents else scrape_item.url
        check_referer = False
        if self.manager.config_manager.settings_data.download_options.skip_referer_seen_before:
            check_referer = await self.manager.db_manager.temp_referer_table.check_referer(posible_referer)

        if check_referer:
            log(f"Skipping {scrape_item.url} as referer has been seen before", 10)
            self.manager.progress_manager.download_progress.add_skipped()
            return True

        return False
