# ruff: noqa: F401
from __future__ import annotations

from typing import TYPE_CHECKING

from cyberdrop_dl.scraper.crawlers.bunkrr_crawler import BunkrrCrawler
from cyberdrop_dl.scraper.crawlers.celebforum_crawler import CelebForumCrawler
from cyberdrop_dl.scraper.crawlers.chevereto_crawler import CheveretoCrawler
from cyberdrop_dl.scraper.crawlers.coomer_crawler import CoomerCrawler
from cyberdrop_dl.scraper.crawlers.cyberdrop_crawler import CyberdropCrawler
from cyberdrop_dl.scraper.crawlers.cyberfile_crawler import CyberfileCrawler
from cyberdrop_dl.scraper.crawlers.ehentai_crawler import EHentaiCrawler
from cyberdrop_dl.scraper.crawlers.erome_crawler import EromeCrawler
from cyberdrop_dl.scraper.crawlers.f95zone_crawler import F95ZoneCrawler
from cyberdrop_dl.scraper.crawlers.fapello_crawler import FapelloCrawler
from cyberdrop_dl.scraper.crawlers.gofile_crawler import GoFileCrawler
from cyberdrop_dl.scraper.crawlers.hotpic_crawler import HotPicCrawler
from cyberdrop_dl.scraper.crawlers.imageban_crawler import ImageBanCrawler
from cyberdrop_dl.scraper.crawlers.imgbb_crawler import ImgBBCrawler
from cyberdrop_dl.scraper.crawlers.imgbox_crawler import ImgBoxCrawler
from cyberdrop_dl.scraper.crawlers.imgur_crawler import ImgurCrawler
from cyberdrop_dl.scraper.crawlers.kemono_crawler import KemonoCrawler
from cyberdrop_dl.scraper.crawlers.leakedmodels_crawler import LeakedModelsCrawler
from cyberdrop_dl.scraper.crawlers.mediafire_crawler import MediaFireCrawler
from cyberdrop_dl.scraper.crawlers.nekohouse_crawler import NekohouseCrawler
from cyberdrop_dl.scraper.crawlers.nudostar_crawler import NudoStarCrawler
from cyberdrop_dl.scraper.crawlers.nudostartv_crawler import NudoStarTVCrawler
from cyberdrop_dl.scraper.crawlers.omegascans_crawler import OmegaScansCrawler
from cyberdrop_dl.scraper.crawlers.pimpandhost_crawler import PimpAndHostCrawler
from cyberdrop_dl.scraper.crawlers.pixeldrain_crawler import PixelDrainCrawler
from cyberdrop_dl.scraper.crawlers.postimg_crawler import PostImgCrawler
from cyberdrop_dl.scraper.crawlers.realbooru_crawler import RealBooruCrawler
from cyberdrop_dl.scraper.crawlers.reddit_crawler import RedditCrawler
from cyberdrop_dl.scraper.crawlers.redgifs_crawler import RedGifsCrawler
from cyberdrop_dl.scraper.crawlers.rule34vault_crawler import Rule34VaultCrawler
from cyberdrop_dl.scraper.crawlers.rule34xxx_crawler import Rule34XXXCrawler
from cyberdrop_dl.scraper.crawlers.rule34xyz_crawler import Rule34XYZCrawler
from cyberdrop_dl.scraper.crawlers.saint_crawler import SaintCrawler
from cyberdrop_dl.scraper.crawlers.scrolller_crawler import ScrolllerCrawler
from cyberdrop_dl.scraper.crawlers.simpcity_crawler import SimpCityCrawler
from cyberdrop_dl.scraper.crawlers.socialmediagirls_crawler import SocialMediaGirlsCrawler
from cyberdrop_dl.scraper.crawlers.tokyomotion_crawler import TokioMotionCrawler
from cyberdrop_dl.scraper.crawlers.toonily_crawler import ToonilyCrawler
from cyberdrop_dl.scraper.crawlers.xbunker_crawler import XBunkerCrawler
from cyberdrop_dl.scraper.crawlers.xbunkr_crawler import XBunkrCrawler
from cyberdrop_dl.scraper.crawlers.xxxbunker_crawler import XXXBunkerCrawler

if TYPE_CHECKING:
    from cyberdrop_dl.scraper.crawler import Crawler

ALL_CRAWLERS: set[type[Crawler]] = {crawler for name, crawler in globals().items() if "Crawler" in name}
DEBUG_CRAWLERS = {SimpCityCrawler}
