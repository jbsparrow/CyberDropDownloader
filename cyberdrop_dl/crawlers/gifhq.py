from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, json_ld
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.url_objects import ScrapeItem


class GifHQCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Post": "/post/<post_id>",
        "Subreddit": (
            "/r/<subreddit>",
            "/r/<subreddit>/best/<period>",
            "/r/<subreddit>/best/<period>?content=images",
            "/r/<subreddit>/best/<period>?content=videos",
        ),
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://gifhq.com")
    DOMAIN: ClassVar[str] = "gifhq"
    FOLDER_DOMAIN: ClassVar[str] = "GifHQ"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["post", _post_id]:
                await self.post(scrape_item)
            case ["r", subreddit]:
                await self.subreddit(scrape_item, subreddit)
            case ["r", subreddit, "best", period]:
                await self.subreddit(scrape_item, subreddit, period)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        soup = await self.request_soup(scrape_item.url)
        try:
            props = json_ld.find_elem(soup, "VideoObject")
        except css.SelectorError:
            props = json_ld.find_elem(soup, "ImageObject")

        src = self.parse_url(props["contentUrl"])
        self.handle_embed(scrape_item.create_child(src))

    @error_handling_wrapper
    async def subreddit(self, scrape_item: ScrapeItem, subreddit: str, period: str | None = None) -> None:
        scrape_item.setup_as_forum(self.create_title(subreddit))
        content = scrape_item.url.query.get("content")
        url = AbsoluteHttpURL("https://gifhq.com/backend.php").update_query(
            device="pc",
            r=subreddit,
            sort="best" if period else "",
            period=period if period in {"allTime", "month", "week", "day"} else "allTime",
            content=content if content in {"all", "videos", "images"} else "all",
            sourced=0,
            windowHeight=500,
            post="",
            sources="",
        )

        for page in itertools.count(int(scrape_item.url.query.get("p", 1))):
            soup = await self.request_soup(url.update_query(p=page))
            for child in self.iter_children(scrape_item, soup, "h5.card-title > a"):
                self.create_task(self.run(child))
