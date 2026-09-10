from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, ClassVar, override

from cyberdrop_dl import aio
from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, extr_text
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Generator

    from cyberdrop_dl.url_objects import ScrapeItem


@Crawler.db_path_builder("path_qs")
class HohojTVCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": "/video?id=<video_id>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://hohoj.tv")
    DOMAIN: ClassVar[str] = "hohoj"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["lang_en", "video"] if video_id := scrape_item.url.query.get("id"):
                return await self.video(scrape_item, int(video_id))
            case _:
                raise ValueError

    @classmethod
    @override
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        url = super().transform_url(url)
        match url.parts[1:]:
            case [*_, "video"] if video_id := url.query.get("id"):
                return (url.origin() / "lang_en" / "video").with_query(id=video_id)
            case _:
                return url

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: int) -> None:
        if await self.check_complete(scrape_item.url):
            return

        video = await self._request_video(video_id)
        scrape_item.uploaded_at = self.parse_iso_date(video.uploaded)
        title = self.create_title(_dvd_code(video.title))
        scrape_item.setup_as_album(title, album_id=str(video_id))

        for img in video.previews:
            if img.name != "no_image.jpg":
                self.create_eager_task(self.direct_file(scrape_item, img))
                scrape_item.add_children()

        m3u8, _ = await self.request_m3u8(video.src)
        filename = self.create_custom_filename(video.src.parent.name, ext := ".mp4")
        await self.handle_file(
            scrape_item.url,
            scrape_item,
            video.title,
            ext,
            m3u8=m3u8,
            custom_filename=filename,
            thumbnail=video.thumb,
        )

    async def _request_video(self, video_id: int) -> Video:
        url = (self.PRIMARY_URL / "lang_en" / "video").with_query(id=video_id)
        embed_url = (self.PRIMARY_URL / "embed").with_query(id=video_id)

        soup, embed = await aio.gather(self.request_soup(url), self.request_text(embed_url), fail_fast=False)
        player = css.select(soup, ".player-col")

        return Video(
            id=video_id,
            title=css.select_text(player, "h5"),
            thumb=self.parse_url(css.select(player, "img", "src")),
            uploaded=css.select_text(player, "div.ms-auto > span"),
            previews=tuple(self.iter_urls(soup, "#previews-list img[src]", "src")),
            src=self.parse_url(extr_text(embed, 'var videoSrc = "', '";')),
        )


@dataclasses.dataclass(slots=True, frozen=True, order=True, kw_only=True)
class Video:
    id: int
    title: str
    uploaded: str
    previews: tuple[AbsoluteHttpURL, ...]
    src: AbsoluteHttpURL
    thumb: AbsoluteHttpURL


def _dvd_code(title: str) -> str:
    if title.startswith("["):
        title = title[title.index("]") + 1 :].strip()
    code, _, rest = title.partition(" ")
    if code.casefold() == "fc2-ppv":
        code = f"{code.upper()} {rest.partition(' ')[0]}"
    if "-" in code or "_" in code:
        return code
    return " ".join(_compose_title(title)).rstrip(":,")


def _compose_title(title: str) -> Generator[str]:
    total = 0
    for word in title.split():
        total += len(word) + 1
        if total > 50:
            break
        yield word
