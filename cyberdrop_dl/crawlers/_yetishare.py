from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, Any, ClassVar

from bs4 import BeautifulSoup

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths, auto_task_id
from cyberdrop_dl.exceptions import DDOSGuardError, PasswordProtectedError, ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selector:
    DOWNLOAD_BUTTON = ".btn-group.responsiveMobileMargin button:-soup-contains('Download')[onclick*='download_token']"
    DROPDOWN_MENU = ".dropdown-menu.dropdown-info a[onclick*='download_token']"
    FILE_NAME = ".image-name-title"
    FILE_UPLOAD_DATE = "td:-soup-contains('Uploaded:') + td"
    FILE_INFO = "script:-soup-contains('showFileInformation')"

    LOAD_IMAGES = "div[class*='page-container'] script:-soup-contains('loadImages')"
    FOLDER_ID = "#folderId"
    _FOLDER_ITEM = "#fileListing [class*=fileItem]"
    FILES = f"{_FOLDER_ITEM}[fileid]"
    SUBFOLDERS = f"{_FOLDER_ITEM}[folderid]"
    FOLDER_TOTAL_PAGES = "input#rspTotalPages"

    LOGIN_FORM = "form#form_login"
    PASSWORD_PROTECTED = "#folderPasswordForm, #filePassword"
    RECAPTCHA = "form[method=POST] script[src*='/recaptcha/api.js']"


class YetiShareCrawler(Crawler, is_abc=True):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Files": (
            "/<file_id>",
            "/<file_id>/<file_name>",
        ),
        "Public Folders": (
            "/folder/<folder_id>",
            "/folder/<folder_id>/<folder_name>",
        ),
        "Shared folders": "/shared/<share_key>",
    }
    _RATE_LIMIT = 5, 1

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        cls.FOLDERS_API_URL = cls.PRIMARY_URL / "account/ajax/load_files"
        cls.FILE_API_URL = cls.PRIMARY_URL / "account/ajax/file_details"
        cls.FOLDER_PASSWORD_API_URL = cls.PRIMARY_URL / "ajax/folder_password_process"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["folder", folder_id, *_]:
                return await self.folder(scrape_item, folder_id)
            case ["shared", folder_id]:
                return await self.folder(scrape_item, folder_id, is_shared=True)
            case [file_id]:
                return await self.file(scrape_item, file_id)
            case [file_id, _]:
                return await self.file(scrape_item, file_id)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem, folder_id: str, is_shared: bool = False) -> None:
        # Make request to update cookies. Access to folders is saved in cookies
        soup = await self.request_soup(scrape_item.url)

        if soup.select_one(Selector.LOGIN_FORM):
            raise ScrapeError(410, "Folder has been deleted")

        if is_shared:
            page_type = "nonaccountshared"
            node_id = ""

        else:
            # ex:  loadImages('folder', '12345', 1, 0, '', {'searchTerm': "", 'filterUploadedDateRange': ""});
            page_type = "folder"
            load_images = get_text_between(soup.select(Selector.LOAD_IMAGES)[-1].text, "loadImages(", ");")
            node_id = load_images.replace("'", "").split(",")[1].strip()

        page = 1
        total_pages = None
        if not scrape_item.album_id:
            scrape_item.setup_as_album("", album_id=folder_id)

        if not is_shared:
            title = css.page_title(soup, self.DOMAIN).removesuffix("Folder").strip()
            scrape_item.add_to_parent_title(self.create_title(title, folder_id))

        for page in itertools.count(1):
            ajax_soup = await self._get_soup_from_ajax_api(
                scrape_item,
                data={
                    "pageType": page_type,
                    "perPage": 0,
                    "filterOrderBy": "",
                    "nodeId": node_id,
                    "pageStart": page,
                },
            )

            if total_pages is None:
                total_pages = int(css.select_one_get_attr(ajax_soup, Selector.FOLDER_TOTAL_PAGES, "value"))

            for file in ajax_soup.select(Selector.FILES):
                file_url = self.parse_url(css.get_attr(file, "dtfullurl"))
                content_id = int(css.get_attr(file, "fileid"))
                new_scrape_item = scrape_item.create_child(file_url)
                new_scrape_item.part_of_album = not is_shared
                self.create_task(self._handle_content_id_task(new_scrape_item, content_id))
                scrape_item.add_children()

            for _, new_scrape_item in self.iter_children(
                scrape_item, ajax_soup, Selector.SUBFOLDERS, attribute="sharing-url"
            ):
                self.create_task(self.run(new_scrape_item))

            if page >= total_pages:
                break

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem, file_id: str) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        soup = await self.request_soup(scrape_item.url)
        if soup.select_one(Selector.PASSWORD_PROTECTED):
            soup = await self._unlock_password_protected_file(scrape_item, file_id)

        _check_is_available(soup)

        content_id = int(
            get_text_between(
                css.select_one_get_text(soup, Selector.FILE_INFO),
                "showFileInformation(",
                ");",
            )
        )

        return await self._handle_content_id(scrape_item, content_id)

    @error_handling_wrapper
    async def _handle_content_id(self, scrape_item: ScrapeItem, content_id: int) -> None:
        soup = await self._get_soup_from_ajax_api(
            scrape_item,
            data={"u": content_id},
            is_file=True,
        )

        download_tag = soup.select_one(Selector.DROPDOWN_MENU) or css.select_one(soup, Selector.DOWNLOAD_BUTTON)

        # Manually parse link. Some URLs are invalid. ex: https://cyberfile.me/7cfu
        # For the download URL, the slug does not actually matter. It can be anything
        raw_link = get_text_between(css.get_attr(download_tag, "onclick"), "('", "');")
        token = raw_link.rpartition("?download_token=")[-1]
        link = self.parse_url(raw_link).with_query(download_token=token)

        scrape_item.possible_datetime = self.parse_date(
            css.select_one_get_text(soup, Selector.FILE_UPLOAD_DATE),
            "%d/%m/%Y %H:%M:%S",
        )

        filename = css.select_one_get_text(soup, Selector.FILE_NAME)
        custom_filename, ext = self.get_filename_and_ext(filename)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    _handle_content_id_task = auto_task_id(_handle_content_id)

    async def _get_soup_from_ajax_api(
        self, scrape_item: ScrapeItem, data: dict[str, Any], *, is_file: bool = False
    ) -> BeautifulSoup:
        async def ajax_api_request() -> BeautifulSoup:
            ajax_url = self.FILE_API_URL if is_file else self.FOLDERS_API_URL
            json_resp: dict[str, str] = await self.request_json(
                ajax_url,
                method="POST",
                data=data,
                headers={"X-Requested-With": "XMLHttpRequest"},
            )

            return BeautifulSoup(json_resp["html"].replace("\\", ""), "html.parser")

        soup = await ajax_api_request()
        if soup.select_one(Selector.PASSWORD_PROTECTED):
            node_id: str = data.get("nodeId") or css.select_one_get_attr(soup, Selector.FOLDER_ID, "value")
            await self._unlock_password_protected_folder(scrape_item, node_id)
            soup = await ajax_api_request()

        _check_is_available(soup)
        return soup

    async def _unlock_password_protected_file(self, scrape_item: ScrapeItem, file_id: str) -> BeautifulSoup:
        password = scrape_item.pop_query("password")
        if not password:
            raise PasswordProtectedError

        password_post_url = (self.PRIMARY_URL / file_id).with_query("pt=")

        content = await self.request_text(
            password_post_url,
            method="POST",
            data={
                "filePassword": password,
                "submitme": 1,
            },
        )
        soup = BeautifulSoup(content, "html.parser")

        if soup.select_one(Selector.PASSWORD_PROTECTED):
            raise PasswordProtectedError("File password is invalid")
        return soup

    async def _unlock_password_protected_folder(self, scrape_item: ScrapeItem, node_id: str) -> None:
        password = scrape_item.pop_query("password")
        if not password:
            raise PasswordProtectedError

        # Make a request with the password. Access to the file/folder will be stored in cookies
        json_resp: dict[str, Any] = await self.request_json(
            self.FOLDER_PASSWORD_API_URL,
            method="POST",
            data={
                "folderPassword": password,
                "folderId": node_id,
                "submitme": 1,
            },
        )
        if not json_resp.get("success"):
            raise PasswordProtectedError(message="Incorrect password")


def _check_is_available(soup: BeautifulSoup):
    if soup.select(Selector.RECAPTCHA):
        raise DDOSGuardError("Google recaptcha found")

    content = soup.get_text()

    if "File has been removed" in content:
        raise ScrapeError(410)

    if "File is not publicly available" in content:
        raise ScrapeError(401)
