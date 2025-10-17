from typing import TYPE_CHECKING

from .bellazon import BellazonCrawler

if TYPE_CHECKING:
    from ._invision import InvisionCrawler

INVISION_CRAWLERS: set[type["InvisionCrawler"]] = {BellazonCrawler}


INVISION_CRAWLERS_MAP = {c.__name__: c for c in INVISION_CRAWLERS}
__all__ = list(INVISION_CRAWLERS_MAP.keys())  # type: ignore[reportUnsupportedDunderAll]
