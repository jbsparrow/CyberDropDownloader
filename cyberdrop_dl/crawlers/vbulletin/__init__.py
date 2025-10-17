from typing import TYPE_CHECKING

from .vipergirls import ViperGirlsCrawler

if TYPE_CHECKING:
    from ._vbulletin import vBulletinCrawler

VBULLETIN_CRAWLERS: set[type["vBulletinCrawler"]] = {ViperGirlsCrawler}

VBULLETIN_CRAWLERS_MAP = {c.__name__: c for c in VBULLETIN_CRAWLERS}
__all__ = list(VBULLETIN_CRAWLERS_MAP.keys())  # type: ignore[reportUnsupportedDunderAll]
