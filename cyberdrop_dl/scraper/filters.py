from __future__ import annotations

from typing import TYPE_CHECKING

import arrow
from yarl import URL

from cyberdrop_dl.clients.errors import NoExtensionError
from cyberdrop_dl.utils.constants import FILE_FORMATS
from cyberdrop_dl.utils.utilities import get_filename_and_ext

if TYPE_CHECKING:
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


def is_valid_url(scrape_item: ScrapeItem) -> bool:
    if not scrape_item.url:
        return False
    if not isinstance(scrape_item.url, URL):
        try:
            scrape_item.url = URL(scrape_item.url)
        except AttributeError:
            return False
    try:
        if not scrape_item.url.host:
            return False
    except AttributeError:
        return False

    return True


def is_outside_date_range(scrape_item: ScrapeItem, before: arrow, after: arrow) -> bool:
    skip = False
    item_date = scrape_item.completed_at or scrape_item.created_at
    if not item_date:
        return False
    if (after and arrow.get(item_date).date() < after) or (before and arrow.get(item_date).date() > before):
        skip = True

    return skip


def is_in_domain_list(scrape_item: ScrapeItem, domain_list: list[str]) -> bool:
    return any(domain in scrape_item.url.host for domain in domain_list)


def remove_trailing_slash(url: URL) -> URL:
    if not str(url).endswith("/"):
        return url

    url_trimmed = url.with_path(url.path[:-1])
    if url.query_string:
        query = url.query_string[:-1]
        url_trimmed = url.with_query(query)

    return url_trimmed


def has_valid_extension(url: URL) -> bool:
    """Checks if the URL has a valid extension."""
    try:
        _, ext = get_filename_and_ext(url.name)
        valid_exts = FILE_FORMATS["Images"] | FILE_FORMATS["Videos"] | FILE_FORMATS["Audio"]
    except NoExtensionError:
        return False
    else:
        return ext in valid_exts
