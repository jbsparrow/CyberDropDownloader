from __future__ import annotations

from typing import TYPE_CHECKING

from cyberdrop_dl.crawlers import CRAWLERS, GenericCrawler
from cyberdrop_dl.crawlers.xenforo import XenforoCrawler

if TYPE_CHECKING:
    from cyberdrop_dl.crawlers import Crawler

forum_crawlers = {crawler for crawler in CRAWLERS if issubclass(crawler, XenforoCrawler)}
website_crawlers = CRAWLERS - forum_crawlers - {GenericCrawler}


def get_supported_sites_from(crawlers: set[type[Crawler]] | set[type[XenforoCrawler]]) -> dict[str, str]:
    support_sites_dict = {}
    for crawler in crawlers:
        site = crawler.DOMAIN or crawler.PRIMARY_URL.host
        support_sites_dict[site] = crawler.PRIMARY_URL.host

    support_sites_dict = {key: support_sites_dict[key] for key in sorted(support_sites_dict)}

    return support_sites_dict


SUPPORTED_FORUMS = get_supported_sites_from(forum_crawlers)
SUPPORTED_WEBSITES = get_supported_sites_from(website_crawlers)
SUPPORTED_SITES = SUPPORTED_FORUMS | SUPPORTED_WEBSITES
SUPPORTED_SITES_DOMAINS = sorted(SUPPORTED_SITES.values())
