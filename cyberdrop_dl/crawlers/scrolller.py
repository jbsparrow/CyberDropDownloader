from __future__ import annotations

import json
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class ScrolllerCrawler(Crawler):
    primary_base_domain = URL("https://scrolller.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "scrolller", "Scrolller")
        self.scrolller_api = URL("https://api.scrolller.com/api/v2/graphql")
        self.headers = {"Content-Type": "application/json"}

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "r" not in scrape_item.url.parts:
            raise ValueError
        await self.subreddit(scrape_item)

    @error_handling_wrapper
    async def subreddit(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        subreddit = scrape_item.url.parts[-1]
        title = self.create_title(subreddit)
        scrape_item.add_to_parent_title(title)
        scrape_item.part_of_album = True
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)

        request_body = {
            "query": """
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
                """,
            "variables": {"url": f"/r/{subreddit}", "filter": None, "hostsDown": None},
        }

        iterator = None
        iterations = 0

        while True:
            request_body["variables"]["iterator"] = iterator
            data = await self.client.post_data(
                self.domain,
                self.scrolller_api,
                data=json.dumps(request_body),
                origin=scrape_item,
            )

            if not data:
                break
            items = data["data"]["getSubreddit"]["children"]["items"]

            for item in items:
                media_sources = [item for item in item["mediaSources"] if ".webp" not in item["url"]]
                if media_sources:
                    url_str = media_sources[-1]["url"]
                    highest_res_image_url = self.parse_url(url_str)
                    filename, ext = self.get_filename_and_ext(highest_res_image_url.name)
                    await self.handle_file(highest_res_image_url, scrape_item, filename, ext)
                    scrape_item.add_children()

            prev_iterator = iterator
            iterator = data["data"]["getSubreddit"]["children"]["iterator"]

            if not items or iterator is None or iterator == prev_iterator or iterations > 0:
                break

            iterations += 1
