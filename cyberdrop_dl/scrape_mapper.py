from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Self, override

from cyberdrop_dl import aio, env, filepath, storage
from cyberdrop_dl.constants import BLOCKED_DOMAINS
from cyberdrop_dl.crawlers import ALLOW_NO_EXT, create_crawlers
from cyberdrop_dl.csv_logs import CSVLogsManager
from cyberdrop_dl.exceptions import JDownloaderError, NoExtensionError
from cyberdrop_dl.logs import log_spacer
from cyberdrop_dl.models.validators import bytesize_to_str
from cyberdrop_dl.progress.scraping import ScrapingUI
from cyberdrop_dl.scrape_source import (
    RetryQuery,
    RetryScrapeSource,
    URLsSource,
    load_items_from_db,
    load_items_from_iterable,
    load_items_from_path,
)
from cyberdrop_dl.url_objects import AbsoluteHttpURL, ScrapeItem, ScrapeItemType
from cyberdrop_dl.utils import remove_trailing_slash
from cyberdrop_dl.utils._url import matches_any_host

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator, Iterator

    from cyberdrop_dl.clients.jd.client import JDownloader
    from cyberdrop_dl.config import Config
    from cyberdrop_dl.config.crawlers import GenericCrawlers
    from cyberdrop_dl.crawlers.crawler import Crawler
    from cyberdrop_dl.crawlers.http_direct import DirectHttpFileCrawler
    from cyberdrop_dl.crawlers.realdebrid import RealDebridCrawler
    from cyberdrop_dl.manager import Manager


logger = logging.getLogger(__name__)


@dataclasses.dataclass(slots=True, eq=False)
class CrawlerFactory:
    manager: Manager
    task_mngr: aio.TaskManager
    tui: ScrapingUI
    _instances: dict[type[Crawler], Crawler] = dataclasses.field(repr=False, default_factory=dict)

    @override
    def __repr__(self) -> str:
        return f"<{type(self).__name__}(instances={len(self._instances):,})>"

    def __getitem__[CrawlerT: Crawler](self, obj: type[CrawlerT]) -> CrawlerT:
        instance = self.get(obj)
        if instance is None:
            raise KeyError(obj)
        return instance

    def __call__[CrawlerT: Crawler](self, obj: type[CrawlerT]) -> CrawlerT:
        instance = self.get(obj)
        if instance is None:
            instance = self._instances[obj] = obj(self.manager, self.task_mngr, self.tui)
        return instance

    def __contains__[CrawlerT: Crawler](self, obj: type[CrawlerT]) -> bool:
        return obj in self._instances

    def get[CrawlerT: Crawler](self, obj: type[CrawlerT]) -> CrawlerT | None:
        return self._instances.get(obj)  # pyright: ignore[reportReturnType]

    def __iter__(self) -> Iterator[Crawler]:
        return iter(self._instances.values())


@dataclasses.dataclass(slots=True)
class ScrapeStats:
    source: Path | str
    count: int = dataclasses.field(init=False, default=0)
    groups: list[str] = dataclasses.field(init=False, default_factory=list)
    url_count: dict[str, int] = dataclasses.field(init=False, default_factory=dict)
    start_time: float = dataclasses.field(init=False, default_factory=time.monotonic)

    @property
    def unique_groups(self) -> list[str]:
        return list(dict.fromkeys(self.groups))

    @property
    def domain_stats(self) -> dict[str, int]:
        return dict(sorted(self.url_count.items(), key=lambda x: x[1]))

    def update(self, item: ScrapeItem) -> None:
        self.count += 1
        if item.folders:
            self.groups.append("/".join(item.folders))


@dataclasses.dataclass(slots=True)
class ScrapeMapper:
    """This class maps links to their respective handlers, or JDownloader if they are unsupported."""

    manager: Manager
    crawlers: dict[str, type[Crawler]] = dataclasses.field(init=False, default_factory=dict)

    task_mngr: aio.TaskManager = dataclasses.field(init=False, default_factory=aio.TaskManager)
    tui: ScrapingUI = dataclasses.field(init=False, default_factory=ScrapingUI)

    logs: CSVLogsManager = dataclasses.field(init=False)
    _direct_http: DirectHttpFileCrawler = dataclasses.field(init=False)
    _jdownloader: JDownloader = dataclasses.field(init=False)
    _real_debrid: RealDebridCrawler = dataclasses.field(init=False)
    _seen_urls: set[AbsoluteHttpURL] = dataclasses.field(init=False, default_factory=set, repr=False)
    _factory: CrawlerFactory = dataclasses.field(init=False)
    _ready: bool = dataclasses.field(init=False, default=False)
    _shutting_down: bool = dataclasses.field(init=False, default=False)

    def shutdown(self) -> None:
        "Shutdown the scrape queue and setup handling of KeyboardInterrupt"
        self._shutting_down = True

    def __repr__(self) -> str:
        fields = (
            f"seen_url={len(self._seen_urls):,}",
            f"crawlers={len(self.crawlers):,}",
            f"tasks_mngr={self.task_mngr!r}",
            f"factory={self._factory!r}",
        )
        return f"<{type(self).__name__}>({', '.join(fields)})"

    def _scrape_queue(self) -> int:
        return sum(crawler.waiting_items for crawler in self._factory)

    def _download_queue(self) -> int:
        total = sum(crawler.downloader.capacity.waiting for crawler in self._factory)
        self.tui.files.stats.queued = total
        return total

    def __post_init__(self) -> None:
        from cyberdrop_dl.clients.jd.client import JDownloader
        from cyberdrop_dl.crawlers.http_direct import DirectHttpFileCrawler
        from cyberdrop_dl.crawlers.realdebrid import RealDebridCrawler

        self._direct_http = DirectHttpFileCrawler(self.manager, self.task_mngr, self.tui)
        self._jdownloader = JDownloader.from_config(self.manager.config)
        self._real_debrid = RealDebridCrawler(self.manager, self.task_mngr, self.tui)
        self._factory = CrawlerFactory(self.manager, self.task_mngr, self.tui)
        self.logs = CSVLogsManager.from_config(self.manager.config, self.task_mngr.logs)
        self.tui.scrape.get_queue = self._scrape_queue
        self.tui.downloads.get_queue = self._download_queue

    async def _init_crawlers(self) -> None:
        crawlers = get_crawlers_mapping()
        self.crawlers.update(crawlers)

        n_generics = 0
        for crawler in _create_generic_crawlers(self.manager.config.crawlers.generic):
            n_generics += 1
            register_crawler(self.crawlers, crawler, from_user=True)

        msg = f"Loaded {len(crawlers) + n_generics:,} crawlers ({len(crawlers):,} concrete, {n_generics:,} generic)"
        logger.debug(msg)

        _disable_crawlers_by_config(self.crawlers, *self.manager.config.crawlers.disabled)
        await self._register_peertube()

    async def _register_peertube(self) -> None:
        # User may have disabled peertube
        if "peertube" not in self.crawlers:
            return

        if "pytest" in sys.modules:
            return

        from cyberdrop_dl.crawlers._peertube import PeerTubeCrawler

        for url in self.manager.config.crawlers.generic.peertube:
            if other := _best_match(self.crawlers, url.host):
                msg = GENERIC_MAP_ERROR.format(url, PeerTubeCrawler.NAME, other.NAME)
                logger.error(msg)
                continue

            self.crawlers[url.host] = PeerTubeCrawler

        peertube = self._factory(PeerTubeCrawler)
        for host in await peertube.get_instances():
            crawler = self.crawlers.setdefault(host, PeerTubeCrawler)
            if crawler.DOMAIN == PeerTubeCrawler.DOMAIN:
                continue

            logger.warning("Found PeerTube site '%s' mapped to a non PeerTube crawler: %s", host, crawler.INFO)

    @contextlib.asynccontextmanager
    async def __call__(self) -> AsyncGenerator[Self]:
        from cyberdrop_dl.downloader.hls import CONCURRENT_SEGMENTS

        assert not self.task_mngr.scrape.done.is_set()
        self.logs.delete_old_logs()
        config = self.manager.config

        _ = CONCURRENT_SEGMENTS.set(config.downloads.concurrent_segments)
        _ = ALLOW_NO_EXT.set(config.filters.allow_files_with_no_extension)

        filepath.setup(config.max_file_name_length, config.max_folder_name_length, config.restrict_path)

        if config.ui.portrait:
            env.FORCE_PORTRAIT_MODE = True

        config.download_folder.mkdir(parents=True, exist_ok=True)
        if config.sort.enabled:
            config.sort.output_folder.mkdir(parents=True, exist_ok=True)

        logger.debug("Using %s as chunk size", bytesize_to_str(self.manager.download_client.chunk_size))
        await self.manager.http_client.load_cookie_files(await self.manager.get_cookie_files())
        self.tui.mode = self.manager.config.ui.mode

        if config.network.dump_responses:
            self.manager.http_client.request_done_callback = self.logs.write_response

        ## IMPORTANT: Order of each context matters!
        with self.__cancel_context():
            async with (
                self.manager.http_client,
                storage.monitor(config.min_free_space),
                self.task_mngr.logs,
                self.task_mngr.downloads,
                self.task_mngr.scrape,
            ):
                self.manager.scrape_mapper = self
                yield self

    @contextlib.contextmanager
    def __cancel_context(self) -> Generator[None]:
        cancelled: bool = False
        with self.tui():
            try:
                yield
            except asyncio.CancelledError:
                # This is a KeyboardInterrupt cause we never cancel tasks
                if not self._shutting_down:
                    raise

                cancelled = True
                self.tui.status.shutdown()

        if cancelled:
            logger.warning("Scraping aborted ('Ctrl + C' pressed)")

    async def __async_init__(self) -> None:
        if self._ready:
            return
        await self._init_crawlers()
        try:
            await self._jdownloader.connect(self.manager.http_client)
        except Exception:
            logger.exception("Failed to connect to jDownloader")

        await self._real_debrid.__async_init__()
        await self._direct_http.__async_post_init__()
        self._ready = True

    async def _wait_until_scrape_is_done(self, stats: ScrapeStats) -> None:
        await self.task_mngr.scrape.done.wait()
        self.tui.hide_scrape_panel()
        stats.url_count.update(
            (crawler.DOMAIN, count) for crawler in self._factory if (count := len(crawler._scraped_items))
        )

    async def run(self, src: URLsSource | RetryScrapeSource | None = None) -> ScrapeStats:
        if self._shutting_down:
            raise RuntimeError("Scraper is already shutting down")

        await self.__async_init__()
        if src is None:
            return ScrapeStats("")

        stats, get_items = _parse_source(src, self.manager)
        async with contextlib.aclosing(get_items) as items:
            self.task_mngr.downloads.create_task(self._wait_until_scrape_is_done(stats))
            max_children = _build_max_children_map(self.manager.config)

            async for item in items:
                item.max_children = max_children
                item.download_folder = self.manager.config.download_folder
                if self._should_scrape(item):
                    stats.update(item)
                    self.task_mngr.scrape.create_task(self._send_to_crawler(item))

        if not stats.count:
            logger.warning("No valid links found")

        return stats

    async def send_to_crawler(self, scrape_item: ScrapeItem) -> None:
        if self._should_scrape(scrape_item):
            await self._send_to_crawler(scrape_item)

    async def _send_to_crawler(self, scrape_item: ScrapeItem) -> None:
        if cls := _best_match(self.crawlers, scrape_item.url.host):
            crawler = self._factory(cls)
            await crawler.__async_init__()
            if crawler.__url_config__.trim:
                scrape_item.url = remove_trailing_slash(scrape_item.url)
            self.task_mngr.scrape.create_task(crawler.run(scrape_item))
            return

        if not self._real_debrid.disabled and self._real_debrid.api.is_supported(scrape_item.url):
            logger.info(f"Using RealDebrid for unsupported URL: {scrape_item.url}")
            self.task_mngr.scrape.create_task(self._real_debrid.run(scrape_item))
            return

        try:
            await self._direct_http.fetch(scrape_item)
        except (NoExtensionError, ValueError):
            pass
        else:
            return

        if self._jdownloader.is_enabled_for(scrape_item.url):
            success = await self._send_to_jdownloader(scrape_item)
            self.tui.scrape_errors.add_unsupported(sent_to_jdownloader=success)
            return

        logger.warning(f"Unsupported URL: {scrape_item.url}")
        self.logs.write_unsupported(scrape_item.url, scrape_item.parents[0] if scrape_item.parents else None)
        self.tui.scrape_errors.add_unsupported()

    async def _send_to_jdownloader(self, scrape_item: ScrapeItem) -> bool:
        logger.info(f"Sending unsupported URL to JDownloader: {scrape_item.url}")
        try:
            await self._jdownloader.send(scrape_item.url, scrape_item.path.as_posix(), scrape_item.path)
        except JDownloaderError as e:
            logger.error(f"Failed to send {scrape_item.url} to JDownloader\n{e.message}")
            origin = scrape_item.parents[0] if scrape_item.parents else None
            self.logs.write_unsupported(scrape_item.url, origin)
            return False
        else:
            return True

    def _should_scrape(self, scrape_item: ScrapeItem) -> bool:
        if scrape_item.url in self._seen_urls:
            return False

        self._seen_urls.add(scrape_item.url)
        if _skip_by_config(scrape_item.url, self.manager.config):
            self.tui.files.stats.skipped += 1
            return False
        return True


def get_crawlers_mapping() -> dict[str, type[Crawler]]:
    from cyberdrop_dl.crawlers import Registry

    crawlers_map: dict[str, type[Crawler]] = {}

    for crawler in sorted(Registry.get_crawlers(), key=lambda c: c.NAME):
        register_crawler(crawlers_map, crawler)

    copy = crawlers_map.copy()
    crawlers_map.clear()
    crawlers_map.update(sorted(copy.items()))
    return crawlers_map


GENERIC_MAP_ERROR = (
    "Unable to assign {} to generic crawler {}. "
    "URL conflicts with URL format of builtin crawler {}. "
    "URL will be ignored"
)


def register_crawler(
    crawlers_map: dict[str, type[Crawler]],
    crawler: type[Crawler],
    *,
    from_user: bool | Literal["raise"] = False,
) -> None:

    for domain in crawler.INFO.scrape_mapper_keys:
        other = crawlers_map.get(domain)
        if from_user:
            if not other and (match := _best_match(crawlers_map, crawler.PRIMARY_URL.host)):
                other = match
            if other:
                msg = GENERIC_MAP_ERROR.format(crawler.PRIMARY_URL, crawler.NAME, other.NAME)
                if from_user == "raise":
                    raise ValueError(msg)
                logger.error(msg)
                continue
            logger.info("Successfully mapped %s to crawler %s", crawler.PRIMARY_URL, crawler.NAME)

        elif other:
            if domain in crawlers_map:
                logger.warning("%s from %s already registered by %s", domain, crawler.NAME, other)

        crawlers_map[domain] = crawler


def _create_generic_crawlers(generics_config: GenericCrawlers) -> Generator[type[Crawler]]:
    from cyberdrop_dl.crawlers._chevereto import CheveretoCrawler

    if generics_config.chevereto:
        yield from create_crawlers(generics_config.chevereto, CheveretoCrawler)

    if generics_config.wordpress_html:
        from cyberdrop_dl.crawlers.wordpress import WordPressHTMLCrawler

        yield from create_crawlers(generics_config.wordpress_html, WordPressHTMLCrawler)

    if generics_config.wordpress_media:
        from cyberdrop_dl.crawlers.wordpress import WordPressMediaCrawler

        yield from create_crawlers(generics_config.wordpress_media, WordPressMediaCrawler)

    if generics_config.discourse:
        from cyberdrop_dl.crawlers.discourse import DiscourseCrawler

        yield from create_crawlers(generics_config.discourse, DiscourseCrawler)

    if generics_config.kvs:
        from cyberdrop_dl.crawlers._kvs import GenericKVSCrawler

        yield from create_crawlers(generics_config.kvs, GenericKVSCrawler)

    if generics_config.video:
        from cyberdrop_dl.crawlers._video import GenericVideoCrawler

        yield from create_crawlers(generics_config.video, GenericVideoCrawler)


def _disable_crawlers_by_config(current_crawlers: dict[str, type[Crawler]], *crawlers_to_disable: str) -> None:
    if not crawlers_to_disable:
        return

    crawlers_to_disable = tuple(sorted({name.casefold() for name in crawlers_to_disable}))

    new_crawlers_mapping = {
        domain: crawler
        for domain, crawler in current_crawlers.items()
        if crawler.INFO.site.casefold() not in crawlers_to_disable
    }

    disabled_crawlers = set(current_crawlers.values()) - set(new_crawlers_mapping.values())

    if len(disabled_crawlers) != len(crawlers_to_disable):
        msg = (
            f"{len(crawlers_to_disable)} Crawler names where provided to disable"
            f", but only {len(disabled_crawlers)} {'is' if len(disabled_crawlers) == 1 else 'are'} a valid crawler's name."
        )
        logger.warning(msg)

    if disabled_crawlers:
        current_crawlers.clear()
        current_crawlers.update(new_crawlers_mapping)
        crawlers_info = "\n".join(
            str({info.site: info.supported_domains}) for info in sorted(c.INFO for c in disabled_crawlers)
        )
        logger.info(f"Crawlers disabled by config: \n{crawlers_info}")

    log_spacer()


def _best_match[T: Crawler | type[Crawler]](crawlers: dict[str, T], domain: str) -> T | None:
    if found := crawlers.get(domain):
        return found

    matches = (host for host, cls in crawlers.items() if host in domain and cls.check_host_match(host))

    try:
        best_match = max(matches, key=len)
    except (ValueError, TypeError):
        return None
    else:
        crawlers[domain] = found = crawlers[best_match]
        return found


def _build_max_children_map(config: Config) -> dict[ScrapeItemType, int]:
    max_children = config.max_children
    return {
        ScrapeItemType.FORUM: max_children.forum,
        ScrapeItemType.FORUM_POST: max_children.forum_post,
        ScrapeItemType.PROFILE: max_children.profile,
        ScrapeItemType.ALBUM: max_children.album,
    }


def _parse_source(
    src: RetryScrapeSource | URLsSource, manager: Manager
) -> tuple[ScrapeStats, AsyncGenerator[ScrapeItem]]:
    match src:
        case RetryScrapeSource():
            source = src.source.value
            query = RetryQuery[src.source.name]
            items = load_items_from_db(
                manager.database.conn,
                query,
                after=src.after,
                before=src.before,
            )
        case Path():
            source = src
            items = load_items_from_path(src)
        case _:
            source = "CLI args"
            items = load_items_from_iterable(src)

    return ScrapeStats(source), items


def _skip_by_config(url: AbsoluteHttpURL, config: Config) -> bool:
    if matches_any_host(url, BLOCKED_DOMAINS):
        logger.info("Skipping %s as it is a blocked domain", url)
        return True

    hosts = config.filters.skip_hosts
    if hosts and matches_any_host(url, hosts):
        logger.info("Skipping %s by skip_hosts config", url)
        return True

    hosts = config.filters.only_hosts
    if hosts and not matches_any_host(url, hosts):
        logger.info("Skipping %s by only_hosts config", url)
        return True

    return False
