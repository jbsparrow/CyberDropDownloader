"""All wordpress sites fruntion exactly the same. We can create subclasses dynamically by their URL"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._wordpress import WordPressHTMLCrawler, WordPressMediaCrawler
from .bestprettygirl import BestPrettyGirlCrawler
from .everia import EveriaClubCrawler

if TYPE_CHECKING:
    from ._wordpress import WordPressBaseCrawler

WP_CRAWLERS: set[type[WordPressBaseCrawler]] = {BestPrettyGirlCrawler, EveriaClubCrawler}
WP_CRAWLERS_MAP = {c.__name__: c for c in WP_CRAWLERS}
__all__ = [*WP_CRAWLERS_MAP.keys(), "WordPressMediaCrawler", "WordPressHTMLCrawler"]  # type: ignore[reportUnsupportedDunderAll]
