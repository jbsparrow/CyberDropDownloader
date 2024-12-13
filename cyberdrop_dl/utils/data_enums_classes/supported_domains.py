from __future__ import annotations

from typing import TYPE_CHECKING

from cyberdrop_dl import __version__ as current_version
from cyberdrop_dl.scraper import ALL_CRAWLERS, DEBUG_CRAWLERS
from cyberdrop_dl.scraper.crawlers.xenforo_crawler import XenforoCrawler
from cyberdrop_dl.utils.constants import PRERELEASE_TAGS

if TYPE_CHECKING:
    from cyberdrop_dl.scraper.crawler import Crawler

crawlers = ALL_CRAWLERS
is_testing = next((tag for tag in PRERELEASE_TAGS if tag in current_version), False)
if not is_testing:
    crawlers -= DEBUG_CRAWLERS

forum_crawlers = {crawler for crawler in crawlers if issubclass(crawler, XenforoCrawler)}
website_crawlers = crawlers - forum_crawlers


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
