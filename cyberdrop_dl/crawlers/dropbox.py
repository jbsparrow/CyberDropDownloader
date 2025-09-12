from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

ZIP_REFERENCE = (
    "[--download-dropbox-folders-as-zip]"
    "(https://script-ware.gitbook.io/cyberdrop-dl/reference/cli-arguments#download-dropbox-folders-as-zip)"
)

PRIMARY_URL = AbsoluteHttpURL("https://www.dropbox.com/")


class DropboxCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "File": (
            "/scl/fi/<file_id>",
            "/s/...",
            "/scl/fo/<token1>/<token2>?preview=<filename>",
        ),
        "Folder": (
            "/scl/fo/<token1>/<token2>",
            "/sh/...",
        ),
        "**NOTE**": f"Folders will be downloaded as a zip file. See: {ZIP_REFERENCE}",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "dropbox"

    @property
    def download_folders(self) -> bool:
        return self.manager.parsed_args.cli_only_args.download_dropbox_folders_as_zip

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """See https://www.dropboxforum.com/discussions/101001012/shared-link--scl-to-s/689070"""

        rlkey = scrape_item.url.query.get("rlkey") or ""
        preview_filename = scrape_item.url.query.get("preview")
        match scrape_item.url.parts[1:]:
            case ["s" | "sh", _, *_]:
                return await self.follow_redirect_w_head(scrape_item)
            case ["scl", "fo", token1, token2]:
                url = PRIMARY_URL / "scl/fo" / token1 / token2
                if preview_filename:
                    url = url.with_query(preview=preview_filename)
                folder_or_file = DropboxItem(None, rlkey, preview_filename, url)
                return await self.folder_or_file(scrape_item, folder_or_file)
            case ["scl", "fi", file_id, *file_name_part]:
                url = PRIMARY_URL / "scl/fi" / file_id
                if preview_filename:
                    file_name = preview_filename
                elif file_name_part:
                    file_name = file_name_part[0]
                else:
                    file_name = None
                file = DropboxItem(file_id, rlkey, file_name, url)
                return await self.folder_or_file(scrape_item, file)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def folder_or_file(self, scrape_item: ScrapeItem, item: DropboxItem) -> None:
        if await self.check_complete_from_referer(item.view_url):
            return

        if not item.rlkey:
            raise ScrapeError(401)

        if item.is_folder and not self.download_folders:
            raise ScrapeError(422, message="Folders download is not enabled")

        scrape_item.url = item.view_url
        if item.filename:
            filename = item.filename
        else:
            async with self.request(item.download_url) as resp:
                filename = resp.filename

        filename, ext = self.get_filename_and_ext(filename)
        await self.handle_file(item.url, scrape_item, filename, ext, debrid_link=item.download_url)


@dataclass(frozen=True, slots=True)
class DropboxItem:
    id: str | None
    rlkey: str
    filename: str | None
    url: AbsoluteHttpURL

    @property
    def is_folder(self) -> bool:
        return not bool(self.filename) and "fi" not in self.url.parts

    @property
    def download_url(self) -> AbsoluteHttpURL:
        return self.url.update_query(dl=1, rlkey=self.rlkey)

    @property
    def view_url(self) -> AbsoluteHttpURL:
        return self.url.with_query(rlkey=self.rlkey, e=1, dl=0)
