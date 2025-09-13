from __future__ import annotations

import datetime
import inspect
from http import HTTPStatus
from typing import TYPE_CHECKING

from yarl import URL

import cyberdrop_dl.constants as constants
from cyberdrop_dl.constants import FILE_FORMATS
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import NoExtensionError
from cyberdrop_dl.utils.utilities import get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import Sequence

    from aiohttp import ClientResponse

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


return_values: dict[AbsoluteHttpURL | str, tuple] = {}

MEDIA_EXTENSIONS = FILE_FORMATS["Images"] | FILE_FORMATS["Videos"] | FILE_FORMATS["Audio"]


def is_valid_url(scrape_item: ScrapeItem) -> bool:
    if not scrape_item.url:
        return False
    if not isinstance(scrape_item.url, URL):
        try:
            scrape_item.url = AbsoluteHttpURL(scrape_item.url)
        except AttributeError:
            return False
    try:
        if not scrape_item.url.host:
            return False
    except AttributeError:
        return False

    return True


def is_outside_date_range(scrape_item: ScrapeItem, before: datetime.date | None, after: datetime.date | None) -> bool:
    skip = False
    item_date = scrape_item.completed_at or scrape_item.created_at
    if not item_date:
        return False
    date = datetime.datetime.fromtimestamp(item_date).date()
    if (after and date < after) or (before and date > before):
        skip = True

    return skip


def is_in_domain_list(scrape_item: ScrapeItem, domain_list: Sequence[str]) -> bool:
    return any(domain in scrape_item.url.host for domain in domain_list)


def has_valid_extension(url: URL, forum: bool = False) -> bool:
    """Checks if the URL has a valid extension."""
    try:
        _, ext = get_filename_and_ext(url.name, forum=forum)
    except NoExtensionError:
        if not forum:
            return has_valid_extension(url, forum=True)
        return False
    else:
        return ext in MEDIA_EXTENSIONS


cache_filter_functions = {}
HTTP_404_LIKE_STATUS = {HTTPStatus.NOT_FOUND, HTTPStatus.GONE, HTTPStatus.UNAVAILABLE_FOR_LEGAL_REASONS}


async def cache_filter_fn(response: ClientResponse) -> bool:
    """Filter function for aiohttp_client_cache"""
    if constants.DISABLE_CACHE:
        return False

    if response.status in HTTP_404_LIKE_STATUS:
        return True

    filter_fn = cache_filter_functions.get(response.url.host)
    if filter_fn:
        return await filter_fn(response) if inspect.iscoroutinefunction(filter_fn) else filter_fn(response)

    return False
