from __future__ import annotations

import binascii
import dataclasses
import itertools
from typing import TYPE_CHECKING, Any, ClassVar

from aiolimiter import AsyncLimiter

from cyberdrop_dl.compat import IntEnum
from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class PostType(IntEnum):
    IMAGE = 0
    VIDEO = 1


class Selectors:
    JW_PLAYER = "script:contains('playerInstance.setup')"
    MODEL_NAME_FROM_PROFILE = "div.actor-name > h1"
    MODEL_NAME_FROM_VIDEO = "h2.actor-title-port"
    MODEL_NAME = f"{MODEL_NAME_FROM_VIDEO}, {MODEL_NAME_FROM_PROFILE}"


_SELECTORS = Selectors()
PRIMARY_URL = AbsoluteHttpURL("https://leakedzone.com")
IMAGES_CDN = AbsoluteHttpURL("https://image-cdn.leakedzone.com/storage/")


@dataclasses.dataclass(frozen=True, slots=True)
class Post:
    id: str
    type: PostType
    created_at: str | None = None
    image: str = ""
    stream_url_play: str = ""

    @staticmethod
    def from_dict(post: dict[str, Any]) -> Post:
        return Post(
            str(post["id"]),
            PostType(post["type"]),
            post["created_at"],
            post["image"].replace("_thumb", ""),
            post.get("stream_url_play", ""),
        )


class LeakedZoneCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": "/<model_id>/video/<video_id>",
        "Model": "/<model_id>",
    }
    DOMAIN: ClassVar[str] = "leakedzone"
    FOLDER_DOMAIN: ClassVar[str] = "LeakedZone"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    IMAGES_CDN: ClassVar[AbsoluteHttpURL] = IMAGES_CDN

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case [_, "video", video_id]:
                return await self.video(scrape_item, video_id)
            case [_]:
                return await self.model(scrape_item)
            case _:
                raise ValueError

    def __post_init__(self) -> None:
        self.request_limiter = AsyncLimiter(3, 10)

    @classmethod
    def get_encoded_video_url(cls, soup: BeautifulSoup) -> str:
        js_text = css.select_one_get_text(soup, _SELECTORS.JW_PLAYER)
        return get_text_between(js_text, 'file: f("', '"),')

    @error_handling_wrapper
    async def model(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        model_name: str = css.select_one_get_text(soup, _SELECTORS.MODEL_NAME_FROM_PROFILE)
        scrape_item.setup_as_profile(self.create_title(model_name))
        headers = {"X-Requested-With": "XMLHttpRequest"}
        for page in itertools.count(1):
            async with self.request_limiter:
                posts = await self.client.get_json(self.DOMAIN, scrape_item.url.with_query(page=page), headers=headers)
            # We may be able to omit the last request by just checking the number of posts
            # Seens to always return 48 posts
            if not posts:
                break
            for post in (Post.from_dict(post) for post in posts):
                if post.type is PostType.VIDEO:
                    post_url = self.PRIMARY_URL / model_name / "video" / post.id
                    await self._handle_video(scrape_item.create_child(post_url), post)
                else:
                    post_url = self.PRIMARY_URL / model_name / "photo" / post.id
                    await self._handle_image(scrape_item.create_child(post_url), post)
                scrape_item.add_children()

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        model_name = css.select_one_get_text(soup, _SELECTORS.MODEL_NAME)
        scrape_item.setup_as_album(self.create_title(model_name))
        encoded_url = self.get_encoded_video_url(soup)
        post = Post(video_id, PostType.VIDEO, stream_url_play=encoded_url)
        await self._handle_video(scrape_item, post, check_referer=False)

    async def _handle_video(self, scrape_item: ScrapeItem, post: Post, check_referer: bool = True) -> None:
        if check_referer and await self.check_complete_from_referer(scrape_item):
            return
        url = self.parse_url(_decode_video_url(post.stream_url_play))
        m3u8 = await self.get_m3u8_from_index_url(url)
        filename, ext = self.get_filename_and_ext(f"{post.id}.mp4")
        if post.created_at:
            scrape_item.possible_datetime = self.parse_iso_date(post.created_at)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext, m3u8=m3u8)

    async def _handle_image(self, scrape_item: ScrapeItem, post: Post) -> None:
        image_url = self.IMAGES_CDN / post.image
        filename, ext = self.get_filename_and_ext(image_url.name)
        assert post.created_at
        scrape_item.possible_datetime = self.parse_iso_date(post.created_at)
        custom_filename = self.create_custom_filename(filename, ext, file_id=post.id)
        await self.handle_file(image_url, scrape_item, filename, ext, custom_filename=custom_filename)


def _decode_video_url(url: str) -> str:
    # cut first and last 16 characters, reverse, base64 decode
    # TODO: Research if this work on any JW Player
    return binascii.a2b_base64(url[-17:15:-1]).decode()
