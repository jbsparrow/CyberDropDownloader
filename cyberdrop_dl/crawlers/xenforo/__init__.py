from .allporncomix import AllPornComixCrawler
from .celebforum import CelebForumCrawler
from .f95zone import F95ZoneCrawler
from .leakedmodels import LeakedModelsCrawler
from .nudostar import NudoStarCrawler
from .simpcity import SimpCityCrawler
from .socialmediagirls import SocialMediaGirlsCrawler
from .titsintops import TitsInTopsCrawler
from .xbunker import XBunkerCrawler
from .xenforo import XenforoCrawler

XF_CRAWLERS: set[type[XenforoCrawler]] = {
    AllPornComixCrawler,
    CelebForumCrawler,
    F95ZoneCrawler,
    LeakedModelsCrawler,
    NudoStarCrawler,
    SimpCityCrawler,
    SocialMediaGirlsCrawler,
    TitsInTopsCrawler,
    XBunkerCrawler,
}

XF_CRAWLERS_MAP = {c.__name__: c for c in XF_CRAWLERS}
__all__ = list(XF_CRAWLERS_MAP.keys())  # type: ignore[reportUnsupportedDunderAll]
