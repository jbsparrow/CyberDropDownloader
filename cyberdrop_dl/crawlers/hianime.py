from __future__ import annotations

import asyncio
import dataclasses
import weakref
from typing import TYPE_CHECKING, Any, ClassVar

import bs4

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths, auto_task_id
from cyberdrop_dl.crawlers.megacloud import MegaCloudCrawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selector:
    EPISODES = "a.ep-item"
    ANIME_NAME = ".film-name.dynamic-name"


@dataclasses.dataclass(slots=True, frozen=True, order=True)
class Anime:
    id: int
    name: str
    episodes: dict[int, Episode]


@dataclasses.dataclass(slots=True, frozen=True, order=True)
class Episode:
    id: int
    number: int
    title: str
    path_qs: str

    @staticmethod
    def from_tag(ep_tag: bs4.Tag) -> Episode:
        return Episode(
            title=css.get_attr(ep_tag, "title"),
            number=int(css.get_attr(ep_tag, "data-number")),
            id=int(css.get_attr(ep_tag, "data-id")),
            path_qs=css.get_attr(ep_tag, "href"),
        )


class HiAnimeCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Anime": "/<name>-<anime_id>",
        "Episode": (
            "/<name>-<anime_id>?ep=<episode_id>",
            "/watch/<name>-<anime_id>?ep=<episode_id>",
        ),
        "**NOTE**": (
            "You can select the language to be downloaded by using a 'lang' query param. "
            "Valid options: 'sub' or 'dub'. Default: 'sub'"
            "If the chosen language is not available, CDL will use the first one available"
        ),
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://hianime.to/")
    OLD_DOMAINS: ClassVar[tuple[str, ...]] = "zoro.to", "aniwatch.to", "aniwatchtv.to"
    DOMAIN: ClassVar[str] = "hianime"

    def __post_init__(self) -> None:
        self._animes: dict[int, Anime] = {}
        self._fetch_anime_locks: weakref.WeakValueDictionary[int, asyncio.Lock] = weakref.WeakValueDictionary()

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        episode = int(scrape_item.url.query.get("ep", 0)) or None
        match scrape_item.url.parts[1:]:
            case ["watch", slug] if anime_id := _parse_anime_id(slug):
                return await self.anime(scrape_item, anime_id, episode)
            case [slug] if anime_id := _parse_anime_id(slug):
                return await self.anime(scrape_item, anime_id, episode)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def anime(self, scrape_item: ScrapeItem, anime_id: int, episode_id: int | None) -> None:
        web_url = scrape_item.url.origin() / scrape_item.url.name
        anime = await self._get_anime(web_url, anime_id)
        scrape_item.setup_as_album(anime.name, album_id=str(anime_id))
        if episode_id:
            episode = anime.episodes[episode_id]
            return await self._episode(scrape_item, episode)

        for episode in anime.episodes.values():
            url = self.parse_url(episode.path_qs, scrape_item.url.origin())
            new_scrape_item = scrape_item.create_child(url)
            self.create_task(self._episode_task(new_scrape_item, episode))
            scrape_item.add_children()

    async def _get_anime(self, web_url: AbsoluteHttpURL, anime_id: int) -> Anime:
        if anime := self._animes.get(anime_id):
            return anime

        if anime_id not in self._fetch_anime_locks:
            lock = asyncio.Lock()
            self._fetch_anime_locks[anime_id] = lock

        async with self._fetch_anime_locks[anime_id]:
            if anime := self._animes.get(anime_id):
                return anime
            self._animes[anime_id] = anime = await self._request_anime_info(web_url, anime_id)
            return anime

    async def request_json(self, url: AbsoluteHttpURL, *args, **kwargs: Any) -> Any:
        # Sometimes they return HTML in the content type headers, but it is JSON
        headers = kwargs.pop("headers", {}) | {"Accept": "application/json"}
        async with self.request(url, *args, headers=headers, **kwargs) as resp:
            return await resp.json(content_type=False)

    async def _request_anime_info(self, web_url: AbsoluteHttpURL, anime_id: int) -> Anime:
        episodes_url = web_url.origin() / "ajax/v2/episode/list/" / str(anime_id)

        anime_soup, episodes_resp = await asyncio.gather(
            self.request_soup(web_url),
            self.request_json(episodes_url),
        )

        return Anime(
            id=anime_id,
            name=css.select_one_get_text(anime_soup, Selector.ANIME_NAME),
            episodes=dict(_parse_episodes_resp(episodes_resp["html"])),
        )

    @error_handling_wrapper
    async def _episode(self, scrape_item: ScrapeItem, episode: Episode) -> None:
        canonical_url = self.parse_url(episode.path_qs, scrape_item.url.origin())
        if await self.check_complete_from_referer(canonical_url):
            return

        servers_url = (scrape_item.url.origin() / "ajax/v2/episode/servers").with_query(episodeId=episode.id)
        server_resp: dict[str, Any] = await self.request_json(servers_url)
        servers: dict[str, str] = dict(_parse_server_resp(server_resp["html"]))

        if not servers:
            raise ScrapeError(422)

        lang = scrape_item.url.query.get("lang") or "sub"
        server_id = servers.get(lang) or next(iter(servers.values()))
        server_url = (scrape_item.url.origin() / "ajax/v2/episode/sources").with_query(id=server_id)
        megacloud_url = self.parse_url((await self.request_json(server_url))["link"])

        video = await MegaCloudCrawler._request_video_source(self, megacloud_url)
        video.title = f"E{str(episode.number).zfill(3)} - {episode.title}"
        video.id = str(episode.id)
        scrape_item.url = canonical_url
        await MegaCloudCrawler._handle_video(self, scrape_item, video)

    _episode_task = auto_task_id(_episode)


def _parse_anime_id(slug: str) -> int | None:
    if "-" in slug:
        name, tail = slug.rsplit("-", 1)
        if name and tail.isdecimal():
            return int(tail)


def _parse_episodes_resp(html: str):
    episodes_soup = bs4.BeautifulSoup(html, "html.parser")
    for ep_tag in episodes_soup.select(Selector.EPISODES):
        episode = Episode.from_tag(ep_tag)
        yield episode.id, episode


def _parse_server_resp(html: str):
    soup = bs4.BeautifulSoup(html, "html.parser")
    for server_type in ("sub", "dub", "raw"):
        if server_tag := soup.select_one(f"div[data-type={server_type}]:-soup-contains('HD-1')"):
            server_id = css.get_attr(server_tag, "data-id")
            yield server_type, server_id
