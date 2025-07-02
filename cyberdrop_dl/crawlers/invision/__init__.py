from ._invision import InvisionCrawler
from .bellazon import BellazonCrawler

INVISION_CRAWLERS: set[type[InvisionCrawler]] = {BellazonCrawler}


INVISION_CRAWLERS_MAP = {c.__name__: c for c in INVISION_CRAWLERS}
__all__ = list(INVISION_CRAWLERS_MAP.keys())  # type: ignore[reportUnsupportedDunderAll]
