from __future__ import annotations

import itertools
import json
from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


GRAPHQL_URL = AbsoluteHttpURL("https://members.luscious.net/graphql/nobatch/")
GRAPHQL_QUERIES = {
    "AlbumGet": "query AlbumGet($id: ID!) {\n  album {\n    get(id: $id) {\n      ... on Album {\n        ...AlbumStandard\n      }\n      ... on MutationError {\n        errors {\n          code\n          message\n        }\n      }\n    }\n  }\n}\n    \n    fragment AlbumStandard on Album {\n  __typename\n  id\n  title\n  labels\n  description\n  created\n  modified\n  like_status\n  number_of_favorites\n  number_of_dislikes\n  moderation_status\n  marked_for_deletion\n  marked_for_processing\n  number_of_pictures\n  number_of_animated_pictures\n  number_of_duplicates\n  slug\n  is_manga\n  url\n  download_url\n  permissions\n  created_by {\n    id\n    url\n    name\n    display_name\n    user_title\n    avatar_url\n  }\n  content {\n    id\n    title\n    url\n  }\n  language {\n    id\n    title\n    url\n  }\n  tags {\n    category\n    text\n    url\n    count\n  }\n  genres {\n    id\n    title\n    slug\n    url\n  }\n  audiences {\n    id\n    title\n    url\n  }\n  is_featured\n  featured_date\n  featured_by {\n    id\n    url\n    name\n    display_name\n    user_title\n    avatar_url\n  }\n}",
    "AlbumListOwnPictures": "query AlbumListOwnPictures($input: PictureListInput!) {\n    picture {\n        list(input: $input) {\n            info {\n                ...FacetCollectionInfo\n            }\n            items {\n                ...PictureStandardWithoutAlbum\n            }\n        }\n    }\n}\n\nfragment FacetCollectionInfo on FacetCollectionInfo {\n    page\n    has_next_page\n    has_previous_page\n    total_items\n    total_pages\n    items_per_page\n    url_complete\n    url_filters_only\n}\n\nfragment PictureStandardWithoutAlbum on Picture {\n    __typename\n    id\n    title\n    created\n    like_status\n    number_of_comments\n    number_of_favorites\n    status\n    width\n    height\n    resolution\n    aspect_ratio\n    url_to_original\n    url_to_video\n    is_animated\n    position\n    tags {\n        id\n        category\n        text\n        url\n    }\n    permissions\n    url\n    thumbnails {\n        width\n        height\n        size\n        url\n    }\n}",
    "PictureListInsideAlbum": "query PictureListInsideAlbum($input: PictureListInput!) {\n  picture {\n    list(input: $input) {\n      info {\n        ...FacetCollectionInfo\n      }\n      items {\n        __typename\n        id\n        title\n        description\n        created\n        like_status\n        number_of_comments\n        number_of_favorites\n        moderation_status\n        width\n        height\n        resolution\n        aspect_ratio\n        url_to_original\n        url_to_video\n        is_animated\n        position\n        permissions\n        url\n        tags {\n          category\n          text\n          url\n        }\n        thumbnails {\n          width\n          height\n          size\n          url\n        }\n      }\n    }\n  }\n}\n    \n    fragment FacetCollectionInfo on FacetCollectionInfo {\n  page\n  has_next_page\n  has_previous_page\n  total_items\n  total_pages\n  items_per_page\n  url_complete\n}",
    "AlbumListWithPeek": "query AlbumListWithPeek($input: AlbumListInput!) {\n    album {\n        list(input: $input) {\n            info {\n                ...FacetCollectionInfo\n            }\n            items {\n                ...AlbumMinimal\n                peek_thumbnails {\n                    width\n                    height\n                    size\n                    url\n                }\n            }\n        }\n    }\n}\n\nfragment FacetCollectionInfo on FacetCollectionInfo {\n    page\n    has_next_page\n    has_previous_page\n    total_items\n    total_pages\n    items_per_page\n    url_complete\n    url_filters_only\n}\n\nfragment AlbumMinimal on Album {\n    __typename\n    id\n    title\n    labels\n    description\n    created\n    modified\n    number_of_favorites\n    number_of_pictures\n    slug\n    is_manga\n    url\n    download_url\n    cover {\n        width\n        height\n        size\n        url\n    }\n    content {\n        id\n        title\n        url\n    }\n    language {\n        id\n        title\n        url\n    }\n    tags {\n        id\n        category\n        text\n        url\n        count\n    }\n    genres {\n        id\n        title\n        slug\n        url\n    }\n    audiences {\n        id\n        title\n        url\n    }\n}",
}

PRIMARY_URL = AbsoluteHttpURL("https://members.luscious.net")


class LusciousCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Album": "/albums/..."}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "luscious"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "albums" not in scrape_item.url.parts or "read" in scrape_item.url.parts:
            raise ValueError
        if scrape_item.url.name == "list":
            return await self.search(scrape_item)
        await self.album(scrape_item)

    def create_graphql_query(self, operation: str, scrape_item: ScrapeItem, page: int = 1) -> str:
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
        album_id = scrape_item.url.parts[-1].split("_")[-1]
        results = await self.get_album_results(album_id)
        title: str = ""
        query_name = "AlbumGet"
        query = self.create_graphql_query(query_name, scrape_item)
        json_resp = await self._api_request(query_name, query)
        title = self.create_title(json_resp["data"]["album"]["get"]["title"], album_id)
        scrape_item.setup_as_album(title, album_id=album_id)

        async for albums in self._pager(scrape_item, is_album=True):
            for album in albums:
                link = self.parse_url(album["url_to_original"])
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

        async for results in self._pager(scrape_item):
            for album in results:
                album_url = self.parse_url(album["url"])
                new_scrape_item = scrape_item.create_child(url=album_url)
                await self.album(new_scrape_item)

    async def _pager(self, scrape_item: ScrapeItem, is_album: bool = False) -> AsyncGenerator[list[dict[str, Any]]]:
        """Generator for album pages."""
        initial_page = int(scrape_item.url.query.get("page", 1))
        query_name = "PictureListInsideAlbum" if is_album else "AlbumListWithPeek"
        data_name = "picture" if is_album else "album"
        for page in itertools.count(initial_page):
            query = self.create_graphql_query(query_name, scrape_item, page)
            results: dict[str, Any] = (await self._api_request(query_name, query))["data"][data_name]["list"]
            yield results["items"]
            if not results["info"]["has_next_page"]:
                break

    async def _api_request(self, query_name: str, query: str) -> dict[str, Any]:
        api_url = GRAPHQL_URL.with_query(operationName=query_name)
        json_resp = await self.request_json(
            api_url,
            method="POST",
            data=query,
            headers={"Content-Type": "application/json"},
        )
        log_debug(json_resp)
        return json_resp
