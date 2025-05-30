from __future__ import annotations

import itertools
import json
from typing import TYPE_CHECKING, Any

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


GRAPHQL_URL = URL("https://members.luscious.net/graphql/nobatch/")
GRAPHQL_QUERIES = {
    "AlbumGet": "query AlbumGet($id: ID!) {\n  album {\n    get(id: $id) {\n      ... on Album {\n        ...AlbumStandard\n      }\n      ... on MutationError {\n        errors {\n          code\n          message\n        }\n      }\n    }\n  }\n}\n    \n    fragment AlbumStandard on Album {\n  __typename\n  id\n  title\n  labels\n  description\n  created\n  modified\n  like_status\n  number_of_favorites\n  number_of_dislikes\n  moderation_status\n  marked_for_deletion\n  marked_for_processing\n  number_of_pictures\n  number_of_animated_pictures\n  number_of_duplicates\n  slug\n  is_manga\n  url\n  download_url\n  permissions\n  created_by {\n    id\n    url\n    name\n    display_name\n    user_title\n    avatar_url\n  }\n  content {\n    id\n    title\n    url\n  }\n  language {\n    id\n    title\n    url\n  }\n  tags {\n    category\n    text\n    url\n    count\n  }\n  genres {\n    id\n    title\n    slug\n    url\n  }\n  audiences {\n    id\n    title\n    url\n  }\n  is_featured\n  featured_date\n  featured_by {\n    id\n    url\n    name\n    display_name\n    user_title\n    avatar_url\n  }\n}",
    "AlbumListOwnPictures": "query AlbumListOwnPictures($input: PictureListInput!) {\n    picture {\n        list(input: $input) {\n            info {\n                ...FacetCollectionInfo\n            }\n            items {\n                ...PictureStandardWithoutAlbum\n            }\n        }\n    }\n}\n\nfragment FacetCollectionInfo on FacetCollectionInfo {\n    page\n    has_next_page\n    has_previous_page\n    total_items\n    total_pages\n    items_per_page\n    url_complete\n    url_filters_only\n}\n\nfragment PictureStandardWithoutAlbum on Picture {\n    __typename\n    id\n    title\n    created\n    like_status\n    number_of_comments\n    number_of_favorites\n    status\n    width\n    height\n    resolution\n    aspect_ratio\n    url_to_original\n    url_to_video\n    is_animated\n    position\n    tags {\n        id\n        category\n        text\n        url\n    }\n    permissions\n    url\n    thumbnails {\n        width\n        height\n        size\n        url\n    }\n}",
    "PictureListInsideAlbum": "query PictureListInsideAlbum($input: PictureListInput!) {\n  picture {\n    list(input: $input) {\n      info {\n        ...FacetCollectionInfo\n      }\n      items {\n        __typename\n        id\n        title\n        description\n        created\n        like_status\n        number_of_comments\n        number_of_favorites\n        moderation_status\n        width\n        height\n        resolution\n        aspect_ratio\n        url_to_original\n        url_to_video\n        is_animated\n        position\n        permissions\n        url\n        tags {\n          category\n          text\n          url\n        }\n        thumbnails {\n          width\n          height\n          size\n          url\n        }\n      }\n    }\n  }\n}\n    \n    fragment FacetCollectionInfo on FacetCollectionInfo {\n  page\n  has_next_page\n  has_previous_page\n  total_items\n  total_pages\n  items_per_page\n  url_complete\n}",
    "AlbumListWithPeek": "query AlbumListWithPeek($input: AlbumListInput!) {\n    album {\n        list(input: $input) {\n            info {\n                ...FacetCollectionInfo\n            }\n            items {\n                ...AlbumMinimal\n                peek_thumbnails {\n                    width\n                    height\n                    size\n                    url\n                }\n            }\n        }\n    }\n}\n\nfragment FacetCollectionInfo on FacetCollectionInfo {\n    page\n    has_next_page\n    has_previous_page\n    total_items\n    total_pages\n    items_per_page\n    url_complete\n    url_filters_only\n}\n\nfragment AlbumMinimal on Album {\n    __typename\n    id\n    title\n    labels\n    description\n    created\n    modified\n    number_of_favorites\n    number_of_pictures\n    slug\n    is_manga\n    url\n    download_url\n    cover {\n        width\n        height\n        size\n        url\n    }\n    content {\n        id\n        title\n        url\n    }\n    language {\n        id\n        title\n        url\n    }\n    tags {\n        id\n        category\n        text\n        url\n        count\n    }\n    genres {\n        id\n        title\n        slug\n        url\n    }\n    audiences {\n        id\n        title\n        url\n    }\n}",
}


class LusciousCrawler(Crawler):
    primary_base_domain = URL("https://members.luscious.net")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "luscious", "Luscious")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""

        if "albums" not in scrape_item.url.parts or "read" in scrape_item.url.parts:
            raise ValueError
        if scrape_item.url.name == "list":
            return await self.search(scrape_item)
        await self.album(scrape_item)

    async def create_graphql_query(self, operation: str, scrape_item: ScrapeItem, page: int = 1) -> str:
        """Creates a graphql query."""
        assert operation in GRAPHQL_QUERIES
        query = scrape_item.url.query
        album_id = scrape_item.album_id
        data: dict[str, Any] = {"id": "1", "operationName": operation, "query": GRAPHQL_QUERIES[operation]}
        if operation == "PictureListInsideAlbum":
            sorting = query.get("sorting", "position")
            only_animated = query.get("only_animated", "false")
            filters = [{"name": "album_id", "value": f"{album_id}"}]
            if only_animated == "true":
                filters.append({"name": "is_animated", "value": "1"})

            data["variables"] = {"input": {"display": sorting, "filters": filters, "items_per_page": 50, "page": page}}

        elif operation == "AlbumGet":
            data["variables"] = {"id": f"{album_id}"}

        elif operation == "AlbumListWithPeek":
            sorting = query.get("display", "date_newest")
            filters = [{"name": i, "value": v} for i, v in query.items() if i not in ("page", "display", "q")]
            data["variables"] = {"input": {"display": sorting, "filters": filters, "page": page}}

        log_debug(data)
        return json.dumps(data)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        album_id = scrape_item.url.parts[-1].split("_")[-1]
        results = await self.get_album_results(album_id)
        title: str = ""
        query_name = "AlbumGet"
        async with self.request_limiter:
            query = await self.create_graphql_query(query_name, scrape_item)
            json_resp = await self.make_post_request(query_name, query)

        title = self.create_title(json_resp["data"]["album"]["get"]["title"], album_id)
        scrape_item.setup_as_album(title, album_id=album_id)

        async for json_resp in self.paginator(scrape_item, is_album=True):
            for item in json_resp["data"]["picture"]["list"]["items"]:
                link = self.parse_url(item["url_to_original"])
                if not self.check_album_results(link, results):
                    filename, ext = self.get_filename_and_ext(link.name)
                    await self.handle_file(link, scrape_item, filename, ext)
                scrape_item.add_children()

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem) -> None:
        query = scrape_item.url.query.get("tagged", "")
        if not query:
            raise ScrapeError(400, "No search query provided")

        async for json_data in self.paginator(scrape_item):
            for item in json_data["data"]["album"]["list"]["items"]:
                album_url = self.parse_url(item["url"])
                new_scrape_item = scrape_item.create_child(url=album_url)
                await self.album(new_scrape_item)

    async def paginator(self, scrape_item: ScrapeItem, is_album: bool = False) -> AsyncGenerator[dict]:
        """Generator for album pages."""
        initial_page = int(scrape_item.url.query.get("page", 1))
        query_name = "PictureListInsideAlbum" if is_album else "AlbumListWithPeek"
        data_name = "picture" if is_album else "album"
        for page in itertools.count(initial_page):
            query: str = await self.create_graphql_query(query_name, scrape_item, page)
            json_resp = await self.make_post_request(query_name, query)
            yield json_resp
            if not json_resp["data"][data_name]["list"]["info"]["has_next_page"]:
                break

    async def make_post_request(self, query_name: str, query: str) -> dict:
        api_url = GRAPHQL_URL.with_query(operationName=query_name)
        headers = {"Content-Type": "application/json"}
        async with self.request_limiter:
            json_resp = await self.client.post_data(self.domain, api_url, data=query, headers=headers)
        log_debug(json_resp)
        return json_resp
