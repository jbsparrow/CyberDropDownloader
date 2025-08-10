from __future__ import annotations

import asyncio
import re
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Self

import aiofiles
import arrow
from yarl import URL

from cyberdrop_dl.constants import BLOCKED_DOMAINS, REGEX_LINKS
from cyberdrop_dl.crawlers import CRAWLERS
from cyberdrop_dl.crawlers._chevereto import CheveretoCrawler
from cyberdrop_dl.crawlers.crawler import Crawler, create_crawlers
from cyberdrop_dl.crawlers.discourse import DiscourseCrawler
from cyberdrop_dl.crawlers.generic import GenericCrawler
from cyberdrop_dl.crawlers.realdebrid import RealDebridCrawler
from cyberdrop_dl.crawlers.wordpress import WordPressHTMLCrawler, WordPressMediaCrawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, MediaItem, ScrapeItem
from cyberdrop_dl.downloader.downloader import Downloader
from cyberdrop_dl.exceptions import JDownloaderError, NoExtensionError
from cyberdrop_dl.scraper.filters import has_valid_extension, is_in_domain_list, is_outside_date_range, is_valid_url
from cyberdrop_dl.scraper.jdownloader import JDownloader
from cyberdrop_dl.utils.logger import log, log_spacer
from cyberdrop_dl.utils.utilities import get_download_path, get_filename_and_ext, remove_trailing_slash

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Sequence
    from types import TracebackType

    from cyberdrop_dl.config.global_model import GenericCrawlerInstances, GlobalSettings
    from cyberdrop_dl.crawlers import Crawler
    from cyberdrop_dl.managers.manager import Manager

existing_crawlers: dict[str, Crawler] = {}
_seen_urls: set[AbsoluteHttpURL] = set()
_crawlers_disabled_at_runtime: set[str] = set()


class ScrapeMapper:
    """This class maps links to their respective handlers, or JDownloader if they are unsupported."""

    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.existing_crawlers: dict[str, Crawler] = {}
        self.no_crawler_downloader = Downloader(self.manager, "no_crawler")
        self.jdownloader = JDownloader(self.manager)
        self.jdownloader_whitelist = self.manager.config_manager.settings_data.runtime_options.jdownloader_whitelist
        self.using_input_file = False
        self.groups = set()
        self.count = 0
        self.fallback_generic: GenericCrawler
        self.real_debrid: RealDebridCrawler

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @property
    def group_count(self) -> int:
        return len(self.groups)

    @property
    def global_settings(self) -> GlobalSettings:
        return self.manager.config_manager.global_settings_data

    @property
    def enable_generic_crawler(self) -> bool:
        return self.global_settings.general.enable_generic_crawler

    def start_scrapers(self) -> None:
        """Starts all scrapers."""
        self.existing_crawlers = get_crawlers_mapping(self.manager)
        self.fallback_generic = GenericCrawler(self.manager)

        generic_crawlers = create_generic_crawlers_by_config(self.global_settings.generic_crawlers_instances)
        for crawler in generic_crawlers:
            register_crawler(self.existing_crawlers, crawler(self.manager), from_user=True)
        disable_crawlers_by_config(self.existing_crawlers, self.global_settings.general.disable_crawlers)

    async def start_real_debrid(self) -> None:
        """Starts RealDebrid."""
        self.existing_crawlers["real-debrid"] = self.real_debrid = real = RealDebridCrawler(self.manager)
        await real.startup()

    async def __aenter__(self) -> Self:
        self.manager.scrape_mapper = self
        await self.manager.client_manager.load_cookie_files()
        await self.manager.client_manager.scraper_session.__aenter__()
        self.manager.task_group = asyncio.TaskGroup()
        await self.manager.task_group.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.manager.task_group.__aexit__(exc_type, exc_val, exc_tb)
        await self.manager.client_manager.scraper_session.__aexit__(exc_type, exc_val, exc_tb)

    async def run(self) -> None:
        """Starts the orchestra."""
        self.start_scrapers()
        await self.manager.db_manager.history_table.update_previously_unsupported(self.existing_crawlers)
        self.jdownloader.connect()
        await self.start_real_debrid()
        self.no_crawler_downloader.startup()
        async for item in self.get_input_items():
            self.manager.task_group.create_task(self.send_to_crawler(item))

    async def get_input_items(self) -> AsyncGenerator[ScrapeItem]:
        item_limit = 0
        if self.manager.parsed_args.cli_only_args.retry_any and self.manager.parsed_args.cli_only_args.max_items_retry:
            item_limit = self.manager.parsed_args.cli_only_args.max_items_retry

        if self.manager.parsed_args.cli_only_args.retry_failed:
            items_generator = self.load_failed_links()
        elif self.manager.parsed_args.cli_only_args.retry_all:
            items_generator = self.load_all_links()
        elif self.manager.parsed_args.cli_only_args.retry_maintenance:
            items_generator = self.load_all_bunkr_failed_links_via_hash()
        else:
            items_generator = self.load_links()

        async for item in items_generator:
            await self.manager.states.RUNNING.wait()
            item.children_limits = self.manager.config_manager.settings_data.download_options.maximum_number_of_children
            if self.filter_items(item):
                if item_limit and self.count >= item_limit:
                    break
                yield item
                self.count += 1

        if not self.count:
            log("No valid links found.", 30)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def parse_input_file_groups(self) -> AsyncGenerator[tuple[str, list[AbsoluteHttpURL]]]:
        """Split URLs from input file by their groups."""
        input_file = self.manager.path_manager.input_file
        if not await asyncio.to_thread(input_file.is_file):
            yield ("", [])
            return

        block_quote = False
        current_group_name = ""
        async with aiofiles.open(input_file, encoding="utf8") as f:
            async for line in f:
                assert isinstance(line, str)

                if line.startswith(("---", "===")):  # New group begins here
                    current_group_name = line.replace("---", "").replace("===", "").strip()

                if current_group_name:
                    self.groups.add(current_group_name)
                    yield (current_group_name, regex_links(line))
                    continue

                block_quote = not block_quote if line == "#\n" else block_quote
                if not block_quote:
                    yield ("", regex_links(line))

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~``

    async def load_links(self) -> AsyncGenerator[ScrapeItem]:
        """Loads links from args / input file."""

        if not self.manager.parsed_args.cli_only_args.links:
            self.using_input_file = True
            async for group_name, urls in self.parse_input_file_groups():
                for url in urls:
                    if not url:
                        continue
                    item = ScrapeItem(url=url)
                    if group_name:
                        item.add_to_parent_title(group_name)
                        item.part_of_album = True
                    yield item

            return

        for url in self.manager.parsed_args.cli_only_args.links:
            yield ScrapeItem(url=url)  # type: ignore

    async def load_failed_links(self) -> AsyncGenerator[ScrapeItem]:
        """Loads failed links from database."""
        entries = await self.manager.db_manager.history_table.get_failed_items()
        for entry in entries:
            yield create_item_from_entry(entry)

    async def load_all_links(self) -> AsyncGenerator[ScrapeItem]:
        """Loads all links from database."""
        after = self.manager.parsed_args.cli_only_args.completed_after or date.fromtimestamp(0)
        before = self.manager.parsed_args.cli_only_args.completed_before or datetime.now().date()
        entries = await self.manager.db_manager.history_table.get_all_items(after, before)
        for entry in entries:
            yield create_item_from_entry(entry)

    async def load_all_bunkr_failed_links_via_hash(self) -> AsyncGenerator[ScrapeItem]:
        """Loads all bunkr links with maintenance hash."""
        entries = await self.manager.db_manager.history_table.get_all_bunkr_failed()
        entries = sorted(set(entries), reverse=True, key=lambda x: arrow.get(x[-1]))
        for entry in entries:
            yield create_item_from_entry(entry)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def filter_and_send_to_crawler(self, scrape_item: ScrapeItem) -> None:
        """Send scrape_item to a supported crawler."""
        if not isinstance(scrape_item.url, URL):
            scrape_item.url = AbsoluteHttpURL(scrape_item.url)
        if self.filter_items(scrape_item):
            await self.send_to_crawler(scrape_item)

    async def send_to_crawler(self, scrape_item: ScrapeItem) -> None:
        """Maps URLs to their respective handlers."""
        scrape_item.url = remove_trailing_slash(scrape_item.url)
        crawler_match = match_url_to_crawler(self.existing_crawlers, scrape_item.url)
        jdownloader_whitelisted = True
        if self.jdownloader_whitelist:
            jdownloader_whitelisted = any(domain in scrape_item.url.host for domain in self.jdownloader_whitelist)

        if crawler_match:
            if not crawler_match.ready:
                await crawler_match.startup()
            self.manager.task_group.create_task(crawler_match.run(scrape_item))
            return

        if not self.real_debrid.disabled and self.real_debrid.is_supported(scrape_item.url):
            log(f"Using RealDebrid for unsupported URL: {scrape_item.url}", 10)
            self.manager.task_group.create_task(self.real_debrid.run(scrape_item))
            return

        if has_valid_extension(scrape_item.url):
            if await self.skip_no_crawler_by_config(scrape_item):
                return

            scrape_item.add_to_parent_title("Loose Files")
            scrape_item.part_of_album = True
            download_folder = get_download_path(self.manager, scrape_item, "no_crawler")
            try:
                filename, _ = get_filename_and_ext(scrape_item.url.name)
            except NoExtensionError:
                filename, _ = get_filename_and_ext(scrape_item.url.name, forum=True)
            media_item = MediaItem.from_item(scrape_item, scrape_item.url, download_folder, filename)
            self.manager.task_group.create_task(self.no_crawler_downloader.run(media_item))
            return

        if self.jdownloader.enabled and jdownloader_whitelisted:
            log(f"Sending unsupported URL to JDownloader: {scrape_item.url}", 20)
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
                self.manager.log_manager.write_unsupported_urls_log(
                    scrape_item.url,
                    scrape_item.parents[0] if scrape_item.parents else None,
                )
            self.manager.progress_manager.scrape_stats_progress.add_unsupported(sent_to_jdownloader=success)
            return

        if self.enable_generic_crawler:
            if not self.fallback_generic.ready:
                await self.fallback_generic.startup()
            self.manager.task_group.create_task(self.fallback_generic.run(scrape_item))
            return

        log(f"Unsupported URL: {scrape_item.url}", 30)
        self.manager.log_manager.write_unsupported_urls_log(
            scrape_item.url,
            scrape_item.parents[0] if scrape_item.parents else None,
        )
        self.manager.progress_manager.scrape_stats_progress.add_unsupported()

    def filter_items(self, scrape_item: ScrapeItem) -> bool:
        """Pre-filter scrape items base on URL."""
        if not is_valid_url(scrape_item):
            return False

        if scrape_item.url in _seen_urls:
            return False
        _seen_urls.add(scrape_item.url)

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

    def disable_crawler(self, domain: str) -> Crawler | None:
        """Disables a crawler at runtime, after the scrape mapper is already running.

        It does not remove the crawler from the crawlers map, it just sets it as `disabled"`

        This has the effect to silently ignore any URL that maps to that crawler, without any "unsupported" or "errors" log messages

        `domain` must match _exactly_, AKA: it must be the value of `crawler.DOMAIN`

        Returns the crawler instance that was disabled (if Any)

        """

        if domain in _crawlers_disabled_at_runtime:
            return

        crawler = next((crawler for crawler in self.existing_crawlers.values() if crawler.DOMAIN == domain), None)
        if crawler and not crawler.disabled:
            crawler.disabled = True
            _crawlers_disabled_at_runtime.add(domain)
            return crawler


def regex_links(line: str) -> list[AbsoluteHttpURL]:
    """Regex grab the links from the URLs.txt file.

    This allows code blocks or full paragraphs to be copy and pasted into the URLs.txt.
    """

    if line.lstrip().rstrip().startswith("#"):
        return []

    yarl_links = []
    all_links = [x.group().replace(".md.", ".") for x in re.finditer(REGEX_LINKS, line)]
    for link in all_links:
        encoded = "%" in link
        yarl_links.append(AbsoluteHttpURL(link, encoded=encoded))
    return yarl_links


def create_item_from_entry(entry: Sequence) -> ScrapeItem:
    url = AbsoluteHttpURL(entry[0])
    retry_path = Path(entry[1])
    item = ScrapeItem(url=url, part_of_album=True, retry=True, retry_path=retry_path)
    completed_at = entry[2]
    created_at = entry[3]
    if not isinstance(item.url, URL):
        item.url = AbsoluteHttpURL(item.url)
    item.completed_at = completed_at
    item.created_at = created_at
    return item


def get_crawlers_mapping(manager: Manager | None = None, include_generics: bool = False) -> dict[str, Crawler]:
    """Retuns a mapping with an instance of all crawlers.

    Crawlers are only created on the first calls. Future calls always return a reference to the same crawlers

    If manager is `None`, the `MOCK_MANAGER` will be used, which means the crawlers won't be able to actually run"""

    from cyberdrop_dl.managers.mock_manager import MOCK_MANAGER

    manager_ = manager or MOCK_MANAGER
    global existing_crawlers
    if not existing_crawlers:
        for crawler in CRAWLERS:
            crawler_instance = crawler(manager_)
            register_crawler(existing_crawlers, crawler_instance, include_generics)
    return existing_crawlers


def register_crawler(
    existing_crawlers: dict[str, Crawler],
    crawler: Crawler,
    include_generics: bool = False,
    from_user: bool | Literal["raise"] = False,
) -> None:
    if crawler.IS_FALLBACK_GENERIC:
        return
    if crawler.IS_GENERIC and include_generics:
        keys = (crawler.GENERIC_NAME,)
    else:
        keys = crawler.SCRAPE_MAPPER_KEYS

    for domain in keys:
        other = existing_crawlers.get(domain)
        if from_user:
            if not other and (match := match_url_to_crawler(existing_crawlers, crawler.PRIMARY_URL)):
                other = match
            if other:
                msg = (
                    f"Unable to assign {crawler.PRIMARY_URL} to generic crawler {crawler.GENERIC_NAME}. "
                    f"URL conflicts with URL format of builtin crawler {other.NAME}. "
                    "URL will be ignored"
                )
                if from_user == "raise":
                    raise ValueError(msg)
                log(msg, 40)
                continue
            else:
                log(f"Successfully mapped {crawler.PRIMARY_URL} to generic crawler {crawler.GENERIC_NAME}")

        elif other:
            msg = f"{domain} from {crawler.NAME} already registered by {other}"
            assert domain not in existing_crawlers, msg
        existing_crawlers[domain] = crawler


def get_unique_crawlers() -> list[Crawler]:
    return sorted(set(get_crawlers_mapping(include_generics=True).values()), key=lambda x: x.INFO.site)


def create_generic_crawlers_by_config(generic_crawlers: GenericCrawlerInstances) -> set[type[Crawler]]:
    new_crawlers: set[type[Crawler]] = set()
    if generic_crawlers.wordpress_html:
        new_crawlers.update(create_crawlers(generic_crawlers.wordpress_html, WordPressHTMLCrawler))
    if generic_crawlers.wordpress_media:
        new_crawlers.update(create_crawlers(generic_crawlers.wordpress_media, WordPressMediaCrawler))
    if generic_crawlers.discourse:
        new_crawlers.update(create_crawlers(generic_crawlers.discourse, DiscourseCrawler))
    if generic_crawlers.chevereto:
        new_crawlers.update(create_crawlers(generic_crawlers.chevereto, CheveretoCrawler))
    return new_crawlers


def disable_crawlers_by_config(existing_crawlers: dict[str, Crawler], crawlers_to_disable: list[str]) -> None:
    if not crawlers_to_disable:
        return

    crawlers_to_disable = sorted({name.casefold() for name in crawlers_to_disable})

    new_crawlers_mapping = {
        key: crawler
        for key, crawler in existing_crawlers.items()
        if crawler.INFO.site.casefold() not in crawlers_to_disable
    }
    disabled_crawlers = set(existing_crawlers.values()) - set(new_crawlers_mapping.values())
    if len(disabled_crawlers) != len(crawlers_to_disable):
        msg = (
            f"{len(crawlers_to_disable)} Crawler names where provided to disable"
            f", but only {len(disabled_crawlers)} {'is' if len(disabled_crawlers) == 1 else 'are'} a valid crawler's name."
        )
        log(msg, 30)

    if disabled_crawlers:
        existing_crawlers.clear()
        existing_crawlers.update(new_crawlers_mapping)
        crawlers_info = "\n".join(
            str({info.site: info.supported_domains}) for info in sorted(crawlers.INFO for crawlers in disabled_crawlers)
        )
        log(f"Crawlers disabled by config: \n{crawlers_info}")
    log_spacer(10)


def match_url_to_crawler(existing_crawlers: dict[str, Crawler], url: AbsoluteHttpURL) -> Crawler | None:
    # match exact domain
    if crawler := existing_crawlers.get(url.host):
        return crawler

    # get most restrictive domain if multiple domain matches
    try:
        domain = max((domain for domain in existing_crawlers if domain in url.host), key=len)
        existing_crawlers[url.host] = crawler = existing_crawlers[domain]
        return crawler
    except (ValueError, TypeError):
        return
