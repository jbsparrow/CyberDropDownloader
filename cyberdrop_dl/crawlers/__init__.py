# ruff: noqa: F401
from __future__ import annotations

from typing import TYPE_CHECKING

from cyberdrop_dl import env

from .archivebate import ArchiveBateCrawler
from .ashemaletube import AShemaleTubeCrawler
from .bestprettygirl import BestPrettyGirlCrawler
from .bunkrr import BunkrrCrawler
from .bunkrr_albums_io import BunkrAlbumsIOCrawler
from .catbox import CatboxCrawler
from .coomer import CoomerCrawler
from .crawler import Crawler
from .cyberdrop import CyberdropCrawler
from .cyberfile import CyberfileCrawler
from .dirtyship import DirtyShipCrawler
from .doodstream import DoodStreamCrawler
from .dropbox import DropboxCrawler
from .e621 import E621Crawler
from .ehentai import EHentaiCrawler
from .eightmuses import EightMusesCrawler
from .eporner import EpornerCrawler
from .erome import EromeCrawler
from .fapello import FapelloCrawler
from .fileditch import FileditchCrawler
from .files_vc import FilesVcCrawler
from .generic import GenericCrawler
from .gofile import GoFileCrawler
from .google_drive import GoogleDriveCrawler
from .hotpic import HotPicCrawler
from .iceyfile import IceyFileCrawler
from .imagebam import ImageBamCrawler
from .imagepond import ImagePondCrawler
from .imgbb import ImgBBCrawler
from .imgbox import ImgBoxCrawler
from .imgur import ImgurCrawler
from .jpg5 import JPG5Crawler
from .kemono import KemonoCrawler
from .luscious import LusciousCrawler
from .mediafire import MediaFireCrawler
from .missav import MissAVCrawler
from .mixdrop import MixDropCrawler
from .motherless import MotherlessCrawler
from .nekohouse import NekohouseCrawler
from .nhentai import NHentaiCrawler
from .noodle_magazine import NoodleMagazineCrawler
from .nudostartv import NudoStarTVCrawler
from .omegascans import OmegaScansCrawler
from .onedrive import OneDriveCrawler
from .pimpandhost import PimpAndHostCrawler
from .pixeldrain import PixelDrainCrawler
from .pixhost import PixHostCrawler
from .pmvhaven import PMVHavenCrawler
from .pornpics import PornPicsCrawler
from .postimg import PostImgCrawler
from .realbooru import RealBooruCrawler
from .reddit import RedditCrawler
from .redgifs import RedGifsCrawler
from .rule34vault import Rule34VaultCrawler
from .rule34video import Rule34VideoCrawler
from .rule34xxx import Rule34XXXCrawler
from .rule34xyz import Rule34XYZCrawler
from .saint import SaintCrawler
from .scrolller import ScrolllerCrawler
from .send_now import SendNowCrawler
from .sendvid import SendVidCrawler
from .sex_dot_com import SexDotComCrawler
from .spankbang import SpankBangCrawler
from .streamable import StreamableCrawler
from .thisvid import ThisVidCrawler
from .tiktok import TikTokCrawler
from .tokyomotion import TokioMotionCrawler
from .toonily import ToonilyCrawler
from .twitter_images import TwimgCrawler
from .wetransfer import WeTransferCrawler
from .xbunkr import XBunkrCrawler
from .xenforo import (
    AllPornComixCrawler,
    BellazonCrawler,
    CelebForumCrawler,
    F95ZoneCrawler,
    LeakedModelsCrawler,
    NudoStarCrawler,
    SimpCityCrawler,
    SocialMediaGirlsCrawler,
    TitsInTopsCrawler,
    XBunkerCrawler,
)
from .xhamster import XhamsterCrawler
from .xxxbunker import XXXBunkerCrawler
from .yandex_disk import YandexDiskCrawler
from .youjizz import YouJizzCrawler

ALL_CRAWLERS: set[type[Crawler]] = {crawler for name, crawler in globals().items() if name.endswith("Crawler")}
ALL_CRAWLERS = ALL_CRAWLERS - {Crawler}
DEBUG_CRAWLERS = {SimpCityCrawler, BunkrAlbumsIOCrawler, MissAVCrawler}
CRAWLERS = ALL_CRAWLERS - DEBUG_CRAWLERS

if env.ENABLE_DEBUG_CRAWLERS == "d396ab8c85fcb1fecd22c8d9b58acf944a44e6d35014e9dd39e42c9a64091eda":
    CRAWLERS.update(DEBUG_CRAWLERS)
