from __future__ import annotations

import json
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

DEFAULT_QUERY = """
    query SubredditQuery(
        $url: String!
        $filter: SubredditPostFilter
        $iterator: String
    ) {
        getSubreddit(url: $url) {
            title
            children(
                limit: 10000
                iterator: $iterator
                filter: $filter
                disabledHosts: null
            ) {
                iterator
                items {
                    title
                    mediaSources {
                        url
                    }
                    blurredMediaSources {
                        url
                    }
                }
            }
        }
    }
"""

PRIMARY_URL = AbsoluteHttpURL("https://scrolller.com")
API_ENTRYPOINT = AbsoluteHttpURL("https://api.scrolller.com/api/v2/graphql")


class ScrolllerCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Subreddit": "/r/..."}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "scrolller"

    def __post_init__(self) -> None:
        self.headers = {"Content-Type": "application/json"}

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "r" in scrape_item.url.parts:
            return await self.subreddit(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def subreddit(self, scrape_item: ScrapeItem) -> None:
        subreddit = scrape_item.url.parts[-1]
        title = self.create_title(subreddit)
        scrape_item.setup_as_album(title)

        request_body = {
            "query": DEFAULT_QUERY,
            "variables": {"url": f"/r/{subreddit}", "filter": None, "hostsDown": None},
        }

        iterator = None
        iterations = 0

        while True:
            request_body["variables"]["iterator"] = iterator
            data: dict[str, dict] = (
                await self.request_json(
                    API_ENTRYPOINT,
                    method="POST",
                    data=json.dumps(request_body),
                )
            )["data"]
            items: list[dict] = data["getSubreddit"]["children"]["items"] if data else []
            if not items:
                break

            for item in items:
                link_str = None
                for src in item["mediaSources"]:
                    if ".webp" not in (src_url := src["url"]):
                        link_str = src_url

                if not link_str:
                    continue

                highest_res_image_url = self.parse_url(link_str)
                filename, ext = self.get_filename_and_ext(highest_res_image_url.name)
                await self.handle_file(highest_res_image_url, scrape_item, filename, ext)
                scrape_item.add_children()

            prev_iterator = iterator
            iterator = data["getSubreddit"]["children"]["iterator"]

            if iterator is None or iterator == prev_iterator or iterations > 0:
                break

            iterations += 1
