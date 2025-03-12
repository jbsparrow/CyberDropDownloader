from __future__ import annotations

from json import dumps as dump_json
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cyberdrop_dl.managers.manager import Manager


class LusciousCrawler(Crawler):
    primary_base_domain = URL("https://members.luscious.net")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "luscious", "Luscious")
        self.graphql_url = URL("https://members.luscious.net/graphql/nobatch/")
        self.graphql_queries = {
            "AlbumGet": "query AlbumGet($id: ID!) {\n  album {\n    get(id: $id) {\n      ... on Album {\n        ...AlbumStandard\n      }\n      ... on MutationError {\n        errors {\n          code\n          message\n        }\n      }\n    }\n  }\n}\n    \n    fragment AlbumStandard on Album {\n  __typename\n  id\n  title\n  labels\n  description\n  created\n  modified\n  like_status\n  number_of_favorites\n  number_of_dislikes\n  moderation_status\n  marked_for_deletion\n  marked_for_processing\n  number_of_pictures\n  number_of_animated_pictures\n  number_of_duplicates\n  slug\n  is_manga\n  url\n  download_url\n  permissions\n  created_by {\n    id\n    url\n    name\n    display_name\n    user_title\n    avatar_url\n  }\n  content {\n    id\n    title\n    url\n  }\n  language {\n    id\n    title\n    url\n  }\n  tags {\n    category\n    text\n    url\n    count\n  }\n  genres {\n    id\n    title\n    slug\n    url\n  }\n  audiences {\n    id\n    title\n    url\n  }\n  is_featured\n  featured_date\n  featured_by {\n    id\n    url\n    name\n    display_name\n    user_title\n    avatar_url\n  }\n}",
            "AlbumListOwnPictures": "query AlbumListOwnPictures($input: PictureListInput!) {\n    picture {\n        list(input: $input) {\n            info {\n                ...FacetCollectionInfo\n            }\n            items {\n                ...PictureStandardWithoutAlbum\n            }\n        }\n    }\n}\n\nfragment FacetCollectionInfo on FacetCollectionInfo {\n    page\n    has_next_page\n    has_previous_page\n    total_items\n    total_pages\n    items_per_page\n    url_complete\n    url_filters_only\n}\n\nfragment PictureStandardWithoutAlbum on Picture {\n    __typename\n    id\n    title\n    created\n    like_status\n    number_of_comments\n    number_of_favorites\n    status\n    width\n    height\n    resolution\n    aspect_ratio\n    url_to_original\n    url_to_video\n    is_animated\n    position\n    tags {\n        id\n        category\n        text\n        url\n    }\n    permissions\n    url\n    thumbnails {\n        width\n        height\n        size\n        url\n    }\n}",
            "PictureListInsideAlbum": "query PictureListInsideAlbum($input: PictureListInput!) {\n  picture {\n    list(input: $input) {\n      info {\n        ...FacetCollectionInfo\n      }\n      items {\n        __typename\n        id\n        title\n        description\n        created\n        like_status\n        number_of_comments\n        number_of_favorites\n        moderation_status\n        width\n        height\n        resolution\n        aspect_ratio\n        url_to_original\n        url_to_video\n        is_animated\n        position\n        permissions\n        url\n        tags {\n          category\n          text\n          url\n        }\n        thumbnails {\n          width\n          height\n          size\n          url\n        }\n      }\n    }\n  }\n}\n    \n    fragment FacetCollectionInfo on FacetCollectionInfo {\n  page\n  has_next_page\n  has_previous_page\n  total_items\n  total_pages\n  items_per_page\n  url_complete\n}",
            "AlbumListWithPeek": "query AlbumListWithPeek($input: AlbumListInput!) {\n    album {\n        list(input: $input) {\n            info {\n                ...FacetCollectionInfo\n            }\n            items {\n                ...AlbumMinimal\n                peek_thumbnails {\n                    width\n                    height\n                    size\n                    url\n                }\n            }\n        }\n    }\n}\n\nfragment FacetCollectionInfo on FacetCollectionInfo {\n    page\n    has_next_page\n    has_previous_page\n    total_items\n    total_pages\n    items_per_page\n    url_complete\n    url_filters_only\n}\n\nfragment AlbumMinimal on Album {\n    __typename\n    id\n    title\n    labels\n    description\n    created\n    modified\n    number_of_favorites\n    number_of_pictures\n    slug\n    is_manga\n    url\n    download_url\n    cover {\n        width\n        height\n        size\n        url\n    }\n    content {\n        id\n        title\n        url\n    }\n    language {\n        id\n        title\n        url\n    }\n    tags {\n        id\n        category\n        text\n        url\n        count\n    }\n    genres {\n        id\n        title\n        slug\n        url\n    }\n    audiences {\n        id\n        title\n        url\n    }\n}",
        }

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""

        if "albums" not in scrape_item.url.parts or "read" in scrape_item.url.parts:
            raise ValueError
        if scrape_item.url.parts[-1] == "list":
            return await self.search(scrape_item)
        await self.album(scrape_item)

    async def create_graphql_query(self, operation: str, scrape_item: ScrapeItem, page: int = 1) -> str:
        """Creates a graphql query."""
        query = scrape_item.url.query
        album_id = scrape_item.album_id
        data = {"id": "1", "operationName": operation, "query": self.graphql_queries[operation]}
        if operation == "PictureListInsideAlbum":
            sorting = query.get("sorting", "position")
            only_animated = query.get("only_animated", "false")

            filters = [{"name": "album_id", "value": f"{album_id}"}]
            if only_animated == "true":
                filters.append({"name": "is_animated", "value": "1"})

            data["variables"] = {
                "input": {
                    "display": sorting,
                    "filters": filters,
                    "items_per_page": 50,
                    "page": page,
                }
            }
        elif operation == "AlbumGet":
            data["variables"] = {"id": f"{album_id}"}
        elif operation == "AlbumListWithPeek":
            sorting = query.get("display", "date_newest")

            filters = [{"name": i, "value": v} for i, v in query.items() if i not in ("page", "display", "q")]

            data["variables"] = {
                "input": {
                    "display": sorting,
                    "filters": filters,
                    "page": page,
                }
            }
        return dump_json(data)

    async def paginator(self, scrape_item: ScrapeItem, is_album: bool = False) -> AsyncGenerator[dict]:
        """Generator for album pages."""
        page = int(scrape_item.url.query.get("page", 1))
        query_name = "PictureListInsideAlbum" if is_album else "AlbumListWithPeek"
        data_name = "picture" if is_album else "album"
        while True:
            query = await self.create_graphql_query(query_name, scrape_item, page)
            async with self.request_limiter:
                json_data = await self.client.post_data(
                    self.domain,
                    self.graphql_url.with_query({"operationName": query_name}),
                    data=query,
                    headers_inc={"Content-Type": "application/json"},
                    origin=scrape_item,
                )
            has_next_page = json_data["data"][data_name]["list"]["info"]["has_next_page"]
            yield json_data
            if has_next_page:
                page += 1
                continue
            break

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        album_id = int(scrape_item.url.parts[-1].split("_")[-1])
        results = await self.get_album_results(album_id)
        scrape_item.album_id = album_id
        scrape_item.part_of_album = True
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)

        # Get album information
        async with self.request_limiter:
            query = await self.create_graphql_query("AlbumGet", scrape_item)
            json_data = await self.client.post_data(
                self.domain,
                self.graphql_url.with_query({"operationName": "AlbumGet"}),
                data=query,
                headers_inc={"Content-Type": "application/json"},
                origin=scrape_item,
            )

        album_title = json_data["data"]["album"]["get"]["title"]
        title = self.create_title(album_title, album_id)
        scrape_item.add_to_parent_title(title)

        async for json_data in self.paginator(scrape_item, is_album=True):
            for item in json_data["data"]["picture"]["list"]["items"]:
                link_str: str = item["url_to_original"]
                link = self.parse_url(link_str)
                filename, ext = get_filename_and_ext(link.name)
                if not self.check_album_results(link, results):
                    await self.handle_file(link, scrape_item, filename, ext)
                scrape_item.add_children()

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem) -> None:
        query = scrape_item.url.query.get("tagged", "")
        if not query:
            raise ScrapeError(400, "No search query provided.", origin=scrape_item)

        async for json_data in self.paginator(scrape_item):
            for item in json_data["data"]["album"]["list"]["items"]:
                album_url_str: str = item["url"]
                album_url = self.parse_url(album_url_str)
                new_scrape_item = self.create_scrape_item(
                    parent_scrape_item=scrape_item,
                    url=album_url,
                )
                await self.album(new_scrape_item)
