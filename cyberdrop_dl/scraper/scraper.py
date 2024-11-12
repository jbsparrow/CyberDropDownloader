from __future__ import annotations

import asyncio
import re
from dataclasses import Field
from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles
import arrow
from yarl import URL

from cyberdrop_dl.clients.errors import JDownloaderError
from cyberdrop_dl.downloader.downloader import Downloader
from cyberdrop_dl.scraper.filters import (
    has_valid_extension,
    is_in_domain_list,
    is_outside_date_range,
    is_valid_url,
    remove_trailing_slash,
)
from cyberdrop_dl.scraper.jdownloader import JDownloader
from cyberdrop_dl.utils.constants import BLOCKED_DOMAINS, REGEX_LINKS
from cyberdrop_dl.utils.dataclasses.url_objects import MediaItem, ScrapeItem
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import get_download_path, get_filename_and_ext

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.scraper.crawler import Crawler


class ScrapeMapper:
    """This class maps links to their respective handlers, or JDownloader if they are unsupported."""

    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.mapping = {
            "bunkr": self.bunkr,
            "celebforum": self.celebforum,
            "coomer": self.coomer,
            "cyberdrop": self.cyberdrop,
            "cyberfile": self.cyberfile,
            "e-hentai": self.ehentai,
            "erome": self.erome,
            "f95zone": self.f95zone,
            "fapello": self.fapello,
            "gofile": self.gofile,
            "hotpic": self.hotpic,
            "ibb.co": self.imgbb,
            "imageban": self.imageban,
            "imgbox": self.imgbox,
            "imgur": self.imgur,
            "jpg.church": self.chevereto,
            "kemono": self.kemono,
            "leakedmodels": self.leakedmodels,
            "mediafire": self.mediafire,
            "nekohouse": self.nekohouse,
            "nudostar.com": self.nudostar,
            "nudostar.tv": self.nudostartv,
            "omegascans": self.omegascans,
            "pimpandhost": self.pimpandhost,
            "pixeldrain": self.pixeldrain,
            "postimg": self.postimg,
            "realbooru": self.realbooru,
            "reddit": self.reddit,
            "redgifs": self.redgifs,
            "rule34.xxx": self.rule34xxx,
            "rule34.xyz": self.rule34xyz,
            "rule34vault": self.rule34vault,
            "saint": self.saint,
            "scrolller": self.scrolller,
            "socialmediagirls": self.socialmediagirls,
            "tokyomotion": self.tokyomotion,
            "toonily": self.toonily,
            "xbunker": self.xbunker,
            "xbunkr": self.xbunkr,
            "xxxbunker": self.xxxbunker,
            "simpcity": self.simpcity,
        }

        self.existing_crawlers: dict[str, Crawler] = {}
        self.no_crawler_downloader = Downloader(self.manager, "no_crawler")
        self.jdownloader = JDownloader(self.manager)
        self.jdownloader_whitelist = self.manager.config_manager.settings_data["Runtime_Options"][
            "jdownloader_whitelist"
        ]
        self.lock = asyncio.Lock()
        self.count = 0

    def bunkr(self) -> None:
        """Creates a Bunkr Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.bunkrr_crawler import BunkrrCrawler

        self.existing_crawlers["bunkrr"] = BunkrrCrawler(self.manager)
        self.existing_crawlers["bunkr"] = self.existing_crawlers["bunkrr"]

    def celebforum(self) -> None:
        """Creates a CelebForum Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.celebforum_crawler import CelebForumCrawler

        self.existing_crawlers["celebforum"] = CelebForumCrawler(self.manager)

    def coomer(self) -> None:
        """Creates a Coomer Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.coomer_crawler import CoomerCrawler

        self.existing_crawlers["coomer"] = CoomerCrawler(self.manager)

    def cyberdrop(self) -> None:
        """Creates a Cyberdrop Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.cyberdrop_crawler import CyberdropCrawler

        self.existing_crawlers["cyberdrop"] = CyberdropCrawler(self.manager)

    def cyberfile(self) -> None:
        """Creates a Cyberfile Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.cyberfile_crawler import CyberfileCrawler

        self.existing_crawlers["cyberfile"] = CyberfileCrawler(self.manager)

    def ehentai(self) -> None:
        """Creates a EHentai Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.ehentai_crawler import EHentaiCrawler

        self.existing_crawlers["e-hentai"] = EHentaiCrawler(self.manager)

    def erome(self) -> None:
        """Creates a Erome Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.erome_crawler import EromeCrawler

        self.existing_crawlers["erome"] = EromeCrawler(self.manager)

    def fapello(self) -> None:
        """Creates a Fappelo Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.fapello_crawler import FapelloCrawler

        self.existing_crawlers["fapello"] = FapelloCrawler(self.manager)

    def f95zone(self) -> None:
        """Creates a F95Zone Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.f95zone_crawler import F95ZoneCrawler

        self.existing_crawlers["f95zone"] = F95ZoneCrawler(self.manager)

    def gofile(self) -> None:
        """Creates a GoFile Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.gofile_crawler import GoFileCrawler

        self.existing_crawlers["gofile"] = GoFileCrawler(self.manager)

    def hotpic(self) -> None:
        """Creates a HotPic Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.hotpic_crawler import HotPicCrawler

        self.existing_crawlers["hotpic"] = HotPicCrawler(self.manager)

    def imageban(self) -> None:
        """Creates a ImageBan Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.imageban_crawler import ImageBanCrawler

        self.existing_crawlers["imageban"] = ImageBanCrawler(self.manager)

    def imgbb(self) -> None:
        """Creates a ImgBB Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.imgbb_crawler import ImgBBCrawler

        self.existing_crawlers["ibb.co"] = ImgBBCrawler(self.manager)

    def imgbox(self) -> None:
        """Creates a ImgBox Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.imgbox_crawler import ImgBoxCrawler

        self.existing_crawlers["imgbox"] = ImgBoxCrawler(self.manager)

    def imgur(self) -> None:
        """Creates a Imgur Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.imgur_crawler import ImgurCrawler

        self.existing_crawlers["imgur"] = ImgurCrawler(self.manager)

    def chevereto(self) -> None:
        """Creates a Chevereto Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.chevereto_crawler import CheveretoCrawler

        self.existing_crawlers["jpg.church"] = CheveretoCrawler(self.manager, "jpg.church")
        for domain in CheveretoCrawler.DOMAINS:
            if domain in CheveretoCrawler.JPG_CHURCH_DOMAINS:
                self.existing_crawlers[domain] = self.existing_crawlers["jpg.church"]
            else:
                self.existing_crawlers[domain] = CheveretoCrawler(self.manager, domain)

    def kemono(self) -> None:
        """Creates a Kemono Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.kemono_crawler import KemonoCrawler

        self.existing_crawlers["kemono"] = KemonoCrawler(self.manager)

    def leakedmodels(self) -> None:
        """Creates a LeakedModels Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.leakedmodels_crawler import LeakedModelsCrawler

        self.existing_crawlers["leakedmodels"] = LeakedModelsCrawler(self.manager)

    def mediafire(self) -> None:
        """Creates a MediaFire Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.mediafire_crawler import MediaFireCrawler

        self.existing_crawlers["mediafire"] = MediaFireCrawler(self.manager)

    def nekohouse(self) -> None:
        """Creates a Nekohouse Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.nekohouse_crawler import NekohouseCrawler

        self.existing_crawlers["nekohouse"] = NekohouseCrawler(self.manager)

    def nudostar(self) -> None:
        """Creates a NudoStar Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.nudostar_crawler import NudoStarCrawler

        self.existing_crawlers["nudostar.com"] = NudoStarCrawler(self.manager)

    def nudostartv(self) -> None:
        """Creates a NudoStarTV Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.nudostartv_crawler import NudoStarTVCrawler

        self.existing_crawlers["nudostar.tv"] = NudoStarTVCrawler(self.manager)

    def omegascans(self) -> None:
        """Creates a OmegaScans Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.omegascans_crawler import OmegaScansCrawler

        self.existing_crawlers["omegascans"] = OmegaScansCrawler(self.manager)

    def pimpandhost(self) -> None:
        """Creates a PimpAndHost Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.pimpandhost_crawler import PimpAndHostCrawler

        self.existing_crawlers["pimpandhost"] = PimpAndHostCrawler(self.manager)

    def pixeldrain(self) -> None:
        """Creates a PixelDrain Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.pixeldrain_crawler import PixelDrainCrawler

        self.existing_crawlers["pixeldrain"] = PixelDrainCrawler(self.manager)

    def postimg(self) -> None:
        """Creates a PostImg Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.postimg_crawler import PostImgCrawler

        self.existing_crawlers["postimg"] = PostImgCrawler(self.manager)

    def realbooru(self) -> None:
        """Creates a RealBooru Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.realbooru_crawler import RealBooruCrawler

        self.existing_crawlers["realbooru"] = RealBooruCrawler(self.manager)

    def realdebrid(self) -> None:
        """Creates a RealDebrid Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.realdebrid_crawler import RealDebridCrawler

        self.existing_crawlers["real-debrid"] = RealDebridCrawler(self.manager)

    def reddit(self) -> None:
        """Creates a Reddit Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.reddit_crawler import RedditCrawler

        self.existing_crawlers["reddit"] = RedditCrawler(self.manager)
        self.existing_crawlers["redd.it"] = self.existing_crawlers["reddit"]

    def redgifs(self) -> None:
        """Creates a RedGifs Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.redgifs_crawler import RedGifsCrawler

        self.existing_crawlers["redgifs"] = RedGifsCrawler(self.manager)

    def rule34vault(self) -> None:
        """Creates a Rule34Vault Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.rule34vault_crawler import Rule34VaultCrawler

        self.existing_crawlers["rule34vault"] = Rule34VaultCrawler(self.manager)

    def rule34xxx(self) -> None:
        """Creates a Rule34XXX Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.rule34xxx_crawler import Rule34XXXCrawler

        self.existing_crawlers["rule34.xxx"] = Rule34XXXCrawler(self.manager)

    def rule34xyz(self) -> None:
        """Creates a Rule34XYZ Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.rule34xyz_crawler import Rule34XYZCrawler

        self.existing_crawlers["rule34.xyz"] = Rule34XYZCrawler(self.manager)

    def saint(self) -> None:
        """Creates a Saint Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.saint_crawler import SaintCrawler

        self.existing_crawlers["saint"] = SaintCrawler(self.manager)

    def scrolller(self) -> None:
        """Creates a Scrolller Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.scrolller_crawler import ScrolllerCrawler

        self.existing_crawlers["scrolller"] = ScrolllerCrawler(self.manager)

    def simpcity(self) -> None:
        """Creates a SimpCity Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.simpcity_crawler import SimpCityCrawler

        self.existing_crawlers["simpcity"] = SimpCityCrawler(self.manager)

    def socialmediagirls(self) -> None:
        """Creates a SocialMediaGirls Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.socialmediagirls_crawler import SocialMediaGirlsCrawler

        self.existing_crawlers["socialmediagirls"] = SocialMediaGirlsCrawler(self.manager)

    def tokyomotion(self) -> None:
        """Creates a Tokyomotion Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.tokyomotion_crawler import TokioMotionCrawler

        self.existing_crawlers["tokyomotion"] = TokioMotionCrawler(self.manager)

    def toonily(self) -> None:
        """Creates a Toonily Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.toonily_crawler import ToonilyCrawler

        self.existing_crawlers["toonily"] = ToonilyCrawler(self.manager)

    def xbunker(self) -> None:
        """Creates a XBunker Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.xbunker_crawler import XBunkerCrawler

        self.existing_crawlers["xbunker"] = XBunkerCrawler(self.manager)

    def xbunkr(self) -> None:
        """Creates a XBunkr Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.xbunkr_crawler import XBunkrCrawler

        self.existing_crawlers["xbunkr"] = XBunkrCrawler(self.manager)

    def xxxbunker(self) -> None:
        """Creates a XXXBunker Crawler instance."""
        from cyberdrop_dl.scraper.crawlers.xxxbunker_crawler import XXXBunkerCrawler

        self.existing_crawlers["xxxbunker"] = XXXBunkerCrawler(self.manager)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    def start_scrapers(self) -> None:
        """Starts all scrapers."""
        for domain in self.mapping:
            self.mapping[domain]()

        for crawler in self.existing_crawlers.values():
            if isinstance(crawler.client, Field):
                crawler.startup()

    def start_jdownloader(self) -> None:
        """Starts JDownloader."""
        if self.jdownloader.enabled and isinstance(self.jdownloader.jdownloader_agent, Field):
            self.jdownloader.jdownloader_setup()

    def start_real_debrid(self) -> None:
        """Starts RealDebrid."""
        if isinstance(self.manager.real_debrid_manager.api, Field):
            self.manager.real_debrid_manager.startup()

        if self.manager.real_debrid_manager.enabled:
            self.realdebrid()
            self.existing_crawlers["real-debrid"].startup()

    async def start(self) -> None:
        """Starts the orchestra."""
        self.manager.scrape_mapper = self

        self.start_scrapers()
        self.start_jdownloader()
        self.start_real_debrid()

        self.no_crawler_downloader.startup()

        if self.manager.args_manager.retry_failed:
            await self.load_failed_links()
        elif self.manager.args_manager.retry_all:
            await self.load_all_links()
        elif self.manager.args_manager.retry_maintenance:
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
        if not self.manager.args_manager.other_links:
            links = await self.parse_input_file_groups()

        else:
            links[""].extend(self.manager.args_manager.other_links)

        links = {k: list(filter(None, v)) for k, v in links.items()}
        items = []

        if not links:
            log("No valid links found.", 30)
        for title in links:
            for url in links[title]:
                item = self.create_item_from_link(url)
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
        if self.manager.args_manager.max_items:
            items = items[: self.manager.args_manager.max_items]
        for item in items:
            self.manager.task_group.create_task(self.send_to_crawler(item))

    async def load_all_links(self) -> None:
        """Loads all links from database."""
        entries = await self.manager.db_manager.history_table.get_all_items(
            self.manager.args_manager.after,
            self.manager.args_manager.before,
        )
        items = []
        for entry in entries:
            item = self.create_item_from_entry(entry)
            if self.filter_items(item):
                items.append(item)
        if self.manager.args_manager.max_items:
            items = items[: self.manager.args_manager.max_items]
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
        if self.manager.args_manager.max_items:
            items = items[: self.manager.args_manager.max_items]
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
        item = ScrapeItem(url=link, parent_title="")
        item.completed_at = None
        item.created_at = None
        return item

    @staticmethod
    def create_item_from_entry(entry: list) -> ScrapeItem:
        link = URL(entry[0])
        retry_path = Path(entry[1])
        scrape_item = ScrapeItem(link, parent_title="", part_of_album=True, retry=True, retry_path=retry_path)
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
        supported_domain = next((key for key in self.existing_crawlers if key in scrape_item.url.host), None)
        jdownloader_whitelisted = True
        if self.jdownloader_whitelist:
            jdownloader_whitelisted = any(domain in scrape_item.url.host for domain in self.jdownloader_whitelist)

        if supported_domain:
            scraper = self.existing_crawlers[supported_domain]
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
            media_item = MediaItem(scrape_item.url, scrape_item, download_folder, filename, None)
            self.manager.task_group.create_task(self.no_crawler_downloader.run(media_item))
            return

        if self.jdownloader.enabled and jdownloader_whitelisted:
            log(f"Sending unsupported URL to JDownloader: {scrape_item.url}", 10)
            success = False
            try:
                download_folder = get_download_path(self.manager, scrape_item, "jdownloader")
                relative_download_dir = download_folder.relative_to(self.manager.path_manager.download_dir)
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

        before = self.manager.args_manager.before
        after = self.manager.args_manager.after
        if is_outside_date_range(scrape_item, before, after):
            log(f"Skipping {scrape_item.url} as it is outside of the desired date range", 10)
            return False

        skip_hosts = self.manager.config_manager.settings_data["Ignore_Options"]["skip_hosts"]
        if skip_hosts and is_in_domain_list(scrape_item, skip_hosts):
            log(f"Skipping URL by skip_hosts config: {scrape_item.url}", 10)
            return False

        only_hosts = self.manager.config_manager.settings_data["Ignore_Options"]["only_hosts"]
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
        if self.manager.config_manager.settings_data["Download_Options"]["skip_referer_seen_before"]:
            check_referer = await self.manager.db_manager.temp_referer_table.check_referer(posible_referer)

        if check_referer:
            log(f"Skipping {scrape_item.url} as referer has been seen before", 10)
            self.manager.progress_manager.download_progress.add_skipped()
            return True

        return False
