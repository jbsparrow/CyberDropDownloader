from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, Any, ClassVar

from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.exceptions import PasswordProtectedError, ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selector:
    DOWNLOAD_BUTTON = "div.btn-group.responsiveMobileMargin button:last-of-type"
    FILE_MENU = "ul.dropdown-menu.dropdown-info.account-dropdown-resize-menu li a"
    FILE_NAME = ".image-name-title"
    FILE_UPLOAD_DATE = "td:contains('Uploaded:') + td"

    LOAD_IMAGES = "div[class*='page-container'] script:contains('loadImages')"
    FOLDER_ID = "#folderId"
    FOLDER_ITEM = "#fileListing div[class*=fileItem]"
    FILES = f"{FOLDER_ITEM} [fileid]"
    SUBFOLDERS = f"{FOLDER_ITEM} [folderid]"
    FOLDER_N_PAGES = "a[onclick*=loadImages]"

    LOGIN_FORM = "form#form_login"
    PASSWORD_FORM = "form[method='POST']"
    FOLDER_TOTAL_PAGES = "input#rspTotalPages"
    FILE_INFO = "script:contains('showFileInformation')"


class YetiShareCrawler(Crawler, is_abc=True):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Files": "/<file_id>",
        "Folder": (
            "/folder/<folder_id>",
            "/folder/<folder_id>/<folder_name>",
        ),
        "Shared folder": "/shared/<share_key>",
    }

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        cls.FOLDERS_API_URL = cls.PRIMARY_URL / "account/ajax/load_files"
        cls.FILE_API_URL = cls.PRIMARY_URL / "account/ajax/file_details"
        cls.FOLDER_PASSWORD_API_URL = cls.PRIMARY_URL / "ajax/folder_password_process"

    def __post_init__(self) -> None:
        self.request_limiter = AsyncLimiter(5, 1)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["folder", folder_id, _]:
                return await self.folder(scrape_item, folder_id)
            case ["folder", folder_id]:
                return await self.folder(scrape_item, folder_id)
            case ["shared", folder_id]:
                return await self.folder(scrape_item, folder_id, is_shared=True)
            case [_]:
                return await self.file(scrape_item)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem, folder_id: str, is_shared: bool = False) -> None:
        # Make request to update cookies. Access to folders in saved on cookies
        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        if soup.select_one(Selector.LOGIN_FORM):
            raise ScrapeError(410, "Folder has been deleted")

        if is_shared:
            page_type = "nonaccountshared"
            node_id = ""

        else:
            # ex:  loadImages('folder', '12345', 1, 0, '', {'searchTerm': "", 'filterUploadedDateRange': ""});
            page_type = "folder"
            load_images = get_text_between(soup.select(Selector.LOAD_IMAGES)[-1].text, "loadImages(", ");")
            _, node_id = load_images.replace("'", "").split(",", 1)
            if _is_password_protected(soup):
                await self._unlock_password_protected_folder(scrape_item, node_id)
                async with self.request_limiter:
                    soup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        page = total_pages = 1
        scrape_item.setup_as_album("", album_id=folder_id)

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
            if not is_shared and page == 1:
                title = self.create_title(css.page_title(soup, self.DOMAIN), folder_id)
                scrape_item.add_to_parent_title(title)
                total_pages = int(css.select_one_get_attr(ajax_soup, Selector.FOLDER_TOTAL_PAGES, "value")) + 1

            for _, new_scrape_item in self.iter_children(scrape_item, ajax_soup, Selector.FILES, attribute="dtfullurl"):
                self.create_task(self.run(new_scrape_item))

            for _, new_scrape_item in self.iter_children(
                scrape_item, ajax_soup, Selector.SUBFOLDERS, attribute="sharing-url"
            ):
                self.create_task(self.run(new_scrape_item))

            if page >= total_pages:
                break

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        _check_is_available(soup)
        if _is_password_protected(soup):
            soup = await self._unlock_password_protected_file(scrape_item, soup)

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

        file_tag = soup.select_one(Selector.FILE_MENU) or css.select_one(soup, Selector.DOWNLOAD_BUTTON)
        download_text = css.get_attr(file_tag, "onclick")
        link = self.parse_url(get_text_between(download_text, "'", "'"))

        scrape_item.possible_datetime = self.parse_date(
            css.select_one_get_text(soup, Selector.FILE_UPLOAD_DATE), "%d/%m/%Y %H:%M:%S"
        )
        filename = css.select_one_get_text(soup, Selector.FILE_NAME)
        custom_filename, ext = self.get_filename_and_ext(filename)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    async def _get_soup_from_ajax_api(
        self, scrape_item: ScrapeItem, data: dict[str, Any], *, is_file: bool = False
    ) -> BeautifulSoup:
        async def ajax_api_request() -> BeautifulSoup:
            ajax_url = self.FILE_API_URL if is_file else self.FOLDERS_API_URL
            async with self.request_limiter:
                json_resp: dict[str, str] = await self.client.post_data(
                    self.DOMAIN,
                    ajax_url,
                    data=data,
                    headers={"X-Requested-With": "XMLHttpRequest"},
                )

            return BeautifulSoup(json_resp["html"].replace("\\", ""), "html.parser")

        soup = await ajax_api_request()
        _check_is_available(soup)
        if _is_password_protected(soup):
            node_id: str = data.get("nodeId") or css.select_one_get_attr(soup, Selector.FOLDER_ID, "value")
            await self._unlock_password_protected_folder(scrape_item, node_id)
            soup = await ajax_api_request()

        return soup

    async def _unlock_password_protected_file(self, scrape_item: ScrapeItem, soup: BeautifulSoup) -> BeautifulSoup:
        password = scrape_item.pop_query("password")
        if not password:
            raise PasswordProtectedError

        form = css.select_one(soup, Selector.PASSWORD_FORM)
        # Figure out the format of this URL to build it instead of selecting it
        password_post_url = self.parse_url(css.get_attr(form, "action"))
        async with self.request_limiter:
            resp_bytes = await self.client.post_data_raw(
                self.DOMAIN,
                password_post_url,
                data={"filePassword": password, "submitme": 1},
            )
        new_soup = BeautifulSoup(resp_bytes, "html.parser")

        if _is_password_protected(new_soup):
            raise PasswordProtectedError("File password is invalid")
        return new_soup

    async def _unlock_password_protected_folder(self, scrape_item: ScrapeItem, node_id: str) -> None:
        password = scrape_item.pop_query("password")
        if not password:
            raise PasswordProtectedError

        # Make a request with the password. Access to the file/folder will be stored in cookies
        async with self.request_limiter:
            json_resp: dict = await self.client.post_data(
                self.DOMAIN,
                self.FOLDER_PASSWORD_API_URL,
                data={
                    "folderPassword": password,
                    "folderId": node_id,
                    "submitme": 1,
                },
            )
        if not json_resp.get("success"):
            raise PasswordProtectedError(message="Incorrect password")


def _check_is_available(soup: BeautifulSoup):
    content = soup.get_text()

    if "File has been removed" in content:
        raise ScrapeError(410)

    if "File is not publicly available" in content:
        raise ScrapeError(401)


def _is_password_protected(soup: BeautifulSoup):
    html = soup.get_text()
    return "Enter File Password" in html or "Password Required" in html
