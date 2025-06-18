"""All wordpress sites fruntion exactly the same. We can create subclasses dynamically by their URL"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .bestprettygirl import BestPrettyGirlCrawler

if TYPE_CHECKING:
    from ._wordpress import WordPressBaseCrawler

WP_CRAWLERS: set[type[WordPressBaseCrawler]] = {BestPrettyGirlCrawler}
WP_CRAWLERS_MAP = {c.__name__: c for c in WP_CRAWLERS}
__all__ = list(WP_CRAWLERS_MAP.keys())  # type: ignore[reportUnsupportedDunderAll]
