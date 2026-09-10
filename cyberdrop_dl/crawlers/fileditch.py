from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, override

from cyberdrop_dl import env
from cyberdrop_dl.clients.http import HTTPConfig
from cyberdrop_dl.crawlers import Registry
from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.exceptions import DDOSGuardError, ScrapeError
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, extr_text
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    import bs4

    from cyberdrop_dl.url_objects import ScrapeItem


_HOMEPAGE_CATCH_ALL = "/s21/FHVZKQyAZlIsrneDAsp.jpeg"


@Registry.database.fix_referer
@HTTPConfig(rate_limit=(3, 1))
class FileditchCrawler(Crawler):
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "theditch.st", "fileditch"
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "File": (
            "/file.php?f=<file_id>",
            "/beta123/<file_id>/<name>",
            "/temp/<file_id>/<name>",
            "/alpha7/<file_id>/<name>",
        ),
        "Short URL": "https://theditch.st/<short_id>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://fileditchfiles.me/")
    DOMAIN: ClassVar[str] = "fileditch"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case [_, _, *_]:
                await self.file(scrape_item)
            case [_] if scrape_item.url.host == "theditch.st":
                await self.short_url(scrape_item)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def short_url(self, scrape_item: ScrapeItem) -> None:
        soup = await self.request_soup(scrape_item.url)
        with scrape_item.track_changes:
            scrape_item.url = self.parse_url(css.select(soup, "a#fd-go", "href"))

        self.create_eager_task(self.run(scrape_item))

    @classmethod
    @override
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        url = super().transform_url(url)
        if url.name == "file.php" and (path := url.query.get("f")):
            return url.with_path(path)
        return url

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        src, thumb = await self.request_download(scrape_item.url)
        if src.path == _HOMEPAGE_CATCH_ALL:
            raise ScrapeError(422)

        filename, ext = self.get_filename_and_ext(src.name)
        await self.handle_file(src, scrape_item, filename, ext, thumbnail=thumb)

    async def request_download(self, url: AbsoluteHttpURL) -> tuple[AbsoluteHttpURL, str | None]:
        resp = await self.flaresolverr_request(url, wait=env.FILEDITCH_WAIT)
        soup = await resp.soup()
        if soup.select_one(".gone-path"):
            raise ScrapeError(410)
        if soup.select("form"):
            raise DDOSGuardError("Flaresolverr failed proof of work challenge")
        src = self.parse_url(css.select(soup, "a.btn[download]", "href"))
        _check_url(src)
        return src, _extr_thumb(soup)


def _extr_thumb(soup: bs4.Tag) -> str | None:
    try:
        return extr_text(css.select(soup, ".vposter[style]", "style"), "background-image:url(", ")").strip("'")
    except (css.SelectorError, ValueError):
        pass


def _check_url(url: AbsoluteHttpURL) -> AbsoluteHttpURL:
    for params in [("md5", "expires"), ("exp", "sig")]:
        if all(map(url.query.get, params)):
            return url
    raise ScrapeError(422, f"Unable to extract a valid download URL. Found: {url}")
