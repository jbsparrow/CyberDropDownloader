from __future__ import annotations

from typing import TYPE_CHECKING

from cyberdrop_dl.crawlers import FORUM_CRAWLERS, WEBSITE_CRAWLERS

if TYPE_CHECKING:
    from collections.abc import Iterable

    from cyberdrop_dl.crawlers import Crawler


def get_supported_sites_from(crawlers: Iterable[type[Crawler]]) -> dict[str, str]:
    support_sites_dict = {}
    for crawler in crawlers:
        if crawler.IS_GENERIC:
            continue
        site = crawler.DOMAIN or crawler.PRIMARY_URL.host
        support_sites_dict[site] = crawler.PRIMARY_URL.host

    return {key: support_sites_dict[key] for key in sorted(support_sites_dict)}


SUPPORTED_FORUMS = get_supported_sites_from(FORUM_CRAWLERS)
SUPPORTED_WEBSITES = get_supported_sites_from(WEBSITE_CRAWLERS)
SUPPORTED_SITES = SUPPORTED_FORUMS | SUPPORTED_WEBSITES
SUPPORTED_SITES_DOMAINS = sorted(SUPPORTED_SITES.values())
