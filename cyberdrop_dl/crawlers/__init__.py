# ruff: noqa: F401
from __future__ import annotations

from cyberdrop_dl import env

from ._chevereto import CheveretoCrawler
from .acidimg import AcidImgCrawler
from .archivebate import ArchiveBateCrawler
from .ashemaletube import AShemaleTubeCrawler
from .beeg import BeegComCrawler
from .box_dot_com import BoxDotComCrawler
from .bunkrr import BunkrrCrawler
from .bunkrr_albums_io import BunkrAlbumsIOCrawler
from .buzzheavier import BuzzHeavierCrawler
from .camwhores_dot_tv import CamwhoresTVCrawler
from .catbox import CatboxCrawler
from .coomer import CoomerCrawler
from .crawler import Crawler
from .cyberdrop import CyberdropCrawler
from .cyberfile import CyberfileCrawler
from .dirtyship import DirtyShipCrawler
from .discourse import DISCOURSE_CRAWLERS, DiscourseCrawler
from .doodstream import DoodStreamCrawler
from .dropbox import DropboxCrawler
from .e621 import E621Crawler
from .efukt import EfuktCrawler
from .ehentai import EHentaiCrawler
from .eightmuses import EightMusesCrawler
from .eporner import EpornerCrawler
from .erome import EromeCrawler
from .fapello import FapelloCrawler
from .fileditch import FileditchCrawler
from .files_vc import FilesVcCrawler
from .flugel_anime import FlugelAnimeCrawler
from .fourchan import FourChanCrawler
from .generic import GenericCrawler
from .girlsreleased import GirlsReleasedCrawler
from .gofile import GoFileCrawler
from .google_drive import GoogleDriveCrawler
from .hitomi_la import HitomiLaCrawler
from .hotleak_vip import HotLeakVipCrawler
from .hotpic import HotPicCrawler
from .iceyfile import IceyFileCrawler
from .imagebam import ImageBamCrawler
from .imagepond import ImagePondCrawler
from .imgbb import ImgBBCrawler
from .imgbox import ImgBoxCrawler
from .imgur import ImgurCrawler
from .imx_to import ImxToCrawler
from .incestflix import IncestflixCrawler
from .influencer_bitches import InfluencerBitchesCrawler
from .invision import INVISION_CRAWLERS
from .jpg5 import JPG5Crawler
from .kemono import KemonoCrawler
from .leakedzone import LeakedZoneCrawler
from .luscious import LusciousCrawler
from .mediafire import MediaFireCrawler
from .mega_nz import MegaNzCrawler
from .missav import MissAVCrawler
from .mixdrop import MixDropCrawler
from .motherless import MotherlessCrawler
from .nekohouse import NekohouseCrawler
from .nhentai import NHentaiCrawler
from .noodle_magazine import NoodleMagazineCrawler
from .nudostartv import NudoStarTVCrawler
from .odnoklassniki import OdnoklassnikiCrawler
from .omegascans import OmegaScansCrawler
from .onedrive import OneDriveCrawler
from .pimpandhost import PimpAndHostCrawler
from .pixeldrain import PixelDrainCrawler
from .pixhost import PixHostCrawler
from .pkmncards import PkmncardsCrawler
from .pmvhaven import PMVHavenCrawler
from .pornhub import PornHubCrawler
from .pornpics import PornPicsCrawler
from .porntrex import PorntrexCrawler
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
from .twpornstars import TwPornstarsCrawler
from .vbulletin import VBULLETIN_CRAWLERS
from .vipr_dot_im import ViprImCrawler
from .wetransfer import WeTransferCrawler
from .wordpress import WP_CRAWLERS, WordPressHTMLCrawler, WordPressMediaCrawler
from .xbunkr import XBunkrCrawler
from .xenforo import XF_CRAWLERS, SimpCityCrawler
from .xhamster import XhamsterCrawler
from .xvideos import XVideosCrawler
from .xxxbunker import XXXBunkerCrawler
from .yandex_disk import YandexDiskCrawler
from .youjizz import YouJizzCrawler

FORUM_CRAWLERS = XF_CRAWLERS.union(INVISION_CRAWLERS, DISCOURSE_CRAWLERS, VBULLETIN_CRAWLERS)
GENERIC_CRAWLERS: set[type[Crawler]] = {WordPressHTMLCrawler, WordPressMediaCrawler, DiscourseCrawler, CheveretoCrawler}
ALL_CRAWLERS: set[type[Crawler]] = {
    crawler for name, crawler in globals().items() if name.endswith("Crawler") and crawler is not Crawler
}
ALL_CRAWLERS.update(WP_CRAWLERS, GENERIC_CRAWLERS, FORUM_CRAWLERS)
DEBUG_CRAWLERS = {GirlsReleasedCrawler, SimpCityCrawler, BunkrAlbumsIOCrawler}
if env.ENABLE_DEBUG_CRAWLERS == "d396ab8c85fcb1fecd22c8d9b58acf944a44e6d35014e9dd39e42c9a64091eda":
    CRAWLERS = ALL_CRAWLERS
else:
    CRAWLERS = ALL_CRAWLERS - DEBUG_CRAWLERS

WEBSITE_CRAWLERS = CRAWLERS - FORUM_CRAWLERS - {GenericCrawler}
__all__ = ["ALL_CRAWLERS", "CRAWLERS", "DEBUG_CRAWLERS", "FORUM_CRAWLERS", "Crawler"]
