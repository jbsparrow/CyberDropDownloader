from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import MaxChildrenError
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.dataclasses.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class ScrolllerCrawler(Crawler):
    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "scrolller", "Scrolller")
        self.scrolller_api = URL("https://api.scrolller.com/api/v2/graphql")
        self.headers = {"Content-Type": "application/json"}
        self.request_limiter = AsyncLimiter(10, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        task_id = self.scraping_progress.add_task(scrape_item.url)

        if "r" in scrape_item.url.parts:
            await self.subreddit(scrape_item)
        else:
            log(f"Scrape Failed: Unknown URL Path for {scrape_item.url}", 40)
            self.manager.progress_manager.scrape_stats_progress.add_failure("Unsupported Link")

        self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def subreddit(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        subreddit = scrape_item.url.parts[-1]
        title = self.create_title(subreddit, None, None)
        scrape_item.add_to_parent_title(title)
        scrape_item.part_of_album = True
        scrape_item.type = FILE_HOST_ALBUM
        scrape_item.children = scrape_item.children_limit = 0

        with contextlib.suppress(IndexError, TypeError):
            scrape_item.children_limit = self.manager.config_manager.settings_data["Download_Options"][
                "maximum_number_of_children"
            ][scrape_item.type]

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

            if data:
                items = data["data"]["getSubreddit"]["children"]["items"]

                for item in items:
                    media_sources = [item for item in item["mediaSources"] if ".webp" not in item["url"]]
                    if media_sources:
                        highest_res_image_url = URL(media_sources[-1]["url"])
                        filename, ext = get_filename_and_ext(highest_res_image_url.name)
                        await self.handle_file(highest_res_image_url, scrape_item, filename, ext)
                        if scrape_item.children_limit and scrape_item.children >= scrape_item.children_limit:
                            raise MaxChildrenError(origin=scrape_item)

                prev_iterator = iterator
                iterator = data["data"]["getSubreddit"]["children"]["iterator"]

                if not items or iterator == prev_iterator:
                    break
                if iterations > 0 and iterator is None:
                    break
            else:
                break

            iterations += 1
