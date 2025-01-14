from __future__ import annotations

from typing import TYPE_CHECKING

from cyberdrop_dl.scraper import CRAWLERS
from cyberdrop_dl.scraper.crawlers.xenforo_crawler import XenforoCrawler

if TYPE_CHECKING:
    from cyberdrop_dl.scraper.crawler import Crawler

forum_crawlers = {crawler for crawler in CRAWLERS if issubclass(crawler, XenforoCrawler)}
website_crawlers = CRAWLERS - forum_crawlers


def get_supported_sites_from(crawlers: set[type[Crawler]]) -> dict[str, str]:
    support_sites_dict = {}
    for crawler in crawlers:
        if not crawler.SUPPORTED_SITES or crawler.primary_base_domain:
            site = crawler.domain or crawler.primary_base_domain.host
            support_sites_dict[site] = crawler.primary_base_domain.host
            continue

        for site, domains in crawler.SUPPORTED_SITES.items():
            support_sites_dict[site] = domains[0]

    support_sites_dict = {key: support_sites_dict[key] for key in sorted(support_sites_dict)}

    return support_sites_dict


SUPPORTED_FORUMS = get_supported_sites_from(forum_crawlers)
SUPPORTED_WEBSITES = get_supported_sites_from(website_crawlers)
SUPPORTED_SITES = SUPPORTED_FORUMS | SUPPORTED_WEBSITES
SUPPORTED_SITES_DOMAINS = sorted(SUPPORTED_SITES.values())
