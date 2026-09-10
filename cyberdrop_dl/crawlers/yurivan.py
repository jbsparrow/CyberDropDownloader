from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import dataclasses

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, json_ld, next_js
from cyberdrop_dl.utils.dataclass import deserialize
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.url_objects import ScrapeItem


class YuriVanCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Chapter": "/story/<story_id>/read?chapter<chapter_id>",
        "Video": "/story/<story_id>/chapter/1",
        "Story": "/story/<story_id>",
    }
    DOMAIN: ClassVar[str] = "yurivan"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://www.yurivan.com")

    async def __async_post_init__(self) -> None:
        self.update_cookies({"age_verified": "remember", "yh_sfs": "same-origin"})

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["story", story_id, "read"] if chapter := scrape_item.url.query.get("chapter"):
                return await self.chapter(scrape_item, story_id, int(chapter))
            case ["story", story_id, *_]:
                return await self.story(scrape_item, story_id)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def story(self, scrape_item: ScrapeItem, story_id: str) -> None:
        soup = await self.request_soup(scrape_item.url)
        try:
            video_props = json_ld.find_elem(soup, "VideoObject")
        except css.SelectorError:
            scrape_item.setup_as_album("")
            self._chapters(scrape_item, story_id, soup)
        else:
            await self._video(scrape_item, video_props)

    def _chapters(self, scrape_item: ScrapeItem, story_id: str, soup: BeautifulSoup) -> None:
        selector = f"a[href*='/story/{story_id}/read?chapter=']"
        for new_item in scrape_item.create_children(self.iter_urls(soup, selector)):
            self.create_task(self.run(new_item))
            scrape_item.add_children()

    async def _video(self, scrape_item: ScrapeItem, props: dict[str, Any]) -> None:
        scrape_item.uploaded_at = self.parse_iso_date(props["uploadDate"])
        thumb = self.parse_url(props["thumbnailUrl"])
        m3u8_url = thumb.with_name("playlist.m3u8")
        name: str = props["name"]
        m3u8, info = await self.request_m3u8_playlist(m3u8_url)
        filename = self.create_custom_filename(
            name,
            ext := ".mp4",
            resolution=info.resolution,
            video_codec=info.codecs.video,
            audio_codec=info.codecs.audio,
        )
        await self.handle_file(m3u8_url, scrape_item, name, ext, m3u8=m3u8, custom_filename=filename, thumbnail=thumb)

    @error_handling_wrapper
    async def chapter(self, scrape_item: ScrapeItem, story_id: str, chapter_id: int) -> None:
        chapter_idx = chapter_id - 1
        soup = await self.request_soup(scrape_item.url)
        story = _extract_story(soup, chapter_idx)
        title = self.create_title(story.storyTitle, story_id)
        scrape_item.setup_as_album(title, album_id=story_id)

        chapter = story.chapters[chapter_idx]
        scrape_item.append_folders(self.create_title(chapter.title))
        async with self.new_task_group() as tg:
            for page in chapter.pages:
                tg.create_task(self.direct_file(scrape_item, page.url))
                scrape_item.add_children()


@dataclasses.dataclass(slots=True)
class Story:
    storyId: str  # noqa: N815
    storyTitle: str  # noqa: N815
    chapters: tuple[Chapter, ...]


@dataclasses.dataclass(slots=True)
class Chapter:
    chapter_index: int
    title: str
    cover_url: str
    pages: tuple[Page, ...] = ()


@dataclasses.dataclass(slots=True)
class Page:
    url: AbsoluteHttpURL
    bytes: int


def _extract_story(soup: BeautifulSoup, chapter_index: int) -> Story:
    next_data = next_js.extract(soup)
    for s in next_js.ifind(next_data, "storyId", "storyTitle", "chapters"):
        story = deserialize(Story, s)
        if len(story.chapters) > chapter_index and story.chapters[chapter_index].pages:
            return story
    raise ScrapeError(422, "Unable to extract story info")
