"""All wordpress sites fruntion exactly the same. We can create subclasses dynamically by their URL"""

import re
from typing import NamedTuple, TypeVar

from cyberdrop_dl.crawlers.crawler import SupportedDomains
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from ._wordpress import WordPressAPICrawler, WordPressCrawler
from .bestprettygirl import BestPrettyGirlCrawler

_CrawlerT = TypeVar("_CrawlerT", bound=WordPressCrawler)
_SITE_URLS = []

CRAWLERS_MAP: dict[str, WordPressCrawler] = {}


class Site(NamedTuple):
    PRIMARY_URL: AbsoluteHttpURL
    DOMAIN: str
    SUPPORTED_DOMAINS: SupportedDomains = ()
    FOLDER_DOMAIN: str = ""


# TODO: Move this to core crawler module
def _create_subclass(url_string: str, base_class: type[_CrawlerT]) -> type[_CrawlerT]:
    primary_url = AbsoluteHttpURL(url_string)
    domain = primary_url.host.removeprefix("www.")
    class_name = _make_crawler_name(domain)
    class_attributes = Site(primary_url, domain)._asdict()
    return type(class_name, (base_class,), class_attributes)  # type: ignore[reportReturnType]


def _make_crawler_name(input_string: str) -> str:
    clean_string = re.sub(r"[^a-zA-Z0-9]+", " ", input_string).strip()
    cap_name = clean_string.title().replace(" ", "")
    assert cap_name and cap_name.isalnum(), (
        f"Can not generate a valid class name from {input_string}. Needs to be defined as a concrete class"
    )
    if cap_name[0].isdigit():
        cap_name = "_" + cap_name

    return f"{cap_name}Crawler"


for cls in (_create_subclass(url, WordPressAPICrawler) for url in _SITE_URLS):
    assert cls.__name__ not in CRAWLERS_MAP
    CRAWLERS_MAP[cls.__name__] = cls

globals().update(CRAWLERS_MAP)


__all__ = ["BestPrettyGirlCrawler", *CRAWLERS_MAP.keys()]  # type: ignore[reportUnsupportedDunderAll]
