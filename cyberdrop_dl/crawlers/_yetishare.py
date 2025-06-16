from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, ClassVar

from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.exceptions import PasswordProtectedError, ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


SOUP_ERRORS = {
    410: ["File has been removed"],
    401: ["File is not publicly available"],
}


class Selectors:
    DOWNLOAD_BUTTON = 'div[class="btn-group responsiveMobileMargin"] button'
    FILE_MENU = 'ul[class="dropdown-menu dropdown-info account-dropdown-resize-menu"] li a'
    FILE_NAME = "div.image-name-title"
    FILE_UPLOAD_DATE = "td:contains('Uploaded:') + td"
    FOLDER_ID_JS = "div[class*='page-container'] script:contains('loadImages')"
    FOLDER_ID = "#folderId"
    FOLDER_ITEM = "div[class=fileListing] div[class*=fileItem]"
    FOLDER_N_PAGES = "a[onclick*=loadImages]"
    LOGIN_FORM = "form[id=form_login]"
    PASSWORD_FORM = "form[method='POST']"
    SHARED_N_PAGES = "input[id=rspTotalPages]"
    SHOW_FILE_INFO_JS = "script:contains('showFileInformation')"


_SELECTOR = Selectors()


class YetiShareCrawler(Crawler, is_abc=True):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Files": "/...",
        "Folder": "/folder/...",
        "Shared folder": "/shared/...",
    }

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        cls.folders_api_url = cls.PRIMARY_URL / "account/ajax/load_files"
        cls.files_api_url = cls.PRIMARY_URL / "account/ajax/file_details"
        cls.folder_password_api_url = cls.PRIMARY_URL / "ajax/folder_password_process"

    def __post_init__(self) -> None:
        self.request_limiter = AsyncLimiter(5, 1)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "folder" in scrape_item.url.parts:
            return await self.folder(scrape_item)
        if "shared" in scrape_item.url.parts:
            return await self.shared_folder(scrape_item)
        return await self.file(scrape_item)

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        if soup.select_one(_SELECTOR.LOGIN_FORM):
            raise ScrapeError(410, "Folder has been deleted")

        js_text = soup.select(_SELECTOR.FOLDER_ID_JS)[-1].text
        # ex:  loadImages('folder', '12345', 1, 0, '', {'searchTerm': "", 'filterUploadedDateRange': ""});
        js_text = get_text_between(js_text, "loadImages(", ");")
        _, node_id = js_text.replace("'", "").split(",", 1)
        album_id = scrape_item.url.parts[2]
        title: str = ""
        default_data = {"pageType": "folder", "perPage": 0, "filterOrderBy": ""}
        for page in itertools.count(1):
            data = default_data | {"nodeId": node_id, "pageStart": page}
            ajax_soup, ajax_title = await self.get_soup_from_ajax(data, scrape_item)
            if not title:
                title = self.create_title(ajax_title, album_id)
                scrape_item.setup_as_album(title, album_id=album_id)
                next_page_tag = ajax_soup.select(_SELECTOR.FOLDER_N_PAGES)[-1]
                n_pages_text: str = css.get_attr(next_page_tag, "onclick")
                n_pages = int(n_pages_text.split(",")[2].split(")")[0].strip())

            _ = self.iter_files(scrape_item, ajax_soup)
            if page >= n_pages:
                break

    @error_handling_wrapper
    async def shared_folder(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            await self.client.get_soup(self.DOMAIN, scrape_item.url)

        subfolders = []
        node_id = ""
        album_id = scrape_item.url.parts[2]
        page = 1
        default_data = {"pageType": "nonaccountshared", "perPage": 0, "filterOrderBy": ""}
        while True:
            data = default_data | {"nodeId": node_id, "pageStart": page}
            ajax_soup, ajax_title = await self.get_soup_from_ajax(data, scrape_item)
            if page == 1:
                title = self.create_title(ajax_title, album_id)
                scrape_item.setup_as_album(title, album_id=album_id)
                n_pages = int(css.select_one_get_attr(ajax_soup, _SELECTOR.SHARED_N_PAGES, "value"))

            subfolders.extend(self.iter_files(scrape_item, ajax_soup, iter_subfolders=False))
            page += 1
            if page > n_pages:
                if not subfolders:
                    break
                node_id = str(subfolders.pop(0))
                page = 1

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        def get_content_id(soup: BeautifulSoup) -> int | None:
            if file_info := soup.select_one(_SELECTOR.SHOW_FILE_INFO_JS):
                content_id = get_text_between(file_info.text, "showFileInformation(", ");")
                return int(content_id)

        file_id = scrape_item.url.parts[1]
        canonical_url = self.PRIMARY_URL / file_id
        if await self.check_complete_from_referer(canonical_url):
            return

        password = scrape_item.url.query.get("password", "")
        scrape_item.url = canonical_url
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        if is_password_protected(soup):
            form = soup.select_one(_SELECTOR.PASSWORD_FORM)
            if not form:
                raise PasswordProtectedError("Unable to parse Password Protected File details")

            password_post_url = self.parse_url(css.get_attr(form, "action"))
            data = {"filePassword": password, "submitme": 1}
            async with self.request_limiter:
                resp_bytes = await self.client.post_data_raw(self.DOMAIN, password_post_url, data=data)

            soup = BeautifulSoup(resp_bytes, "html.parser")
            if is_password_protected(soup):
                raise PasswordProtectedError("File password is invalid")

        if content_id := get_content_id(soup):
            return await self.handle_content_id(scrape_item, content_id)

        check_soup_error(soup)
        raise ScrapeError(422, message="contentId not found")

    @error_handling_wrapper
    async def handle_content_id(self, scrape_item: ScrapeItem, content_id: int) -> None:
        data = {"u": content_id}
        ajax_soup, page_title = await self.get_soup_from_ajax(data, scrape_item, is_file=True)

        try:
            file_tag = ajax_soup.select_one(_SELECTOR.FILE_MENU) or ajax_soup.select(_SELECTOR.DOWNLOAD_BUTTON)[-1]
            html_download_text = css.get_attr(file_tag, "onclick")
            link_str = html_download_text.split("'")[1].strip().removesuffix("'")
            link = self.parse_url(link_str)
        except (AttributeError, IndexError, KeyError):
            check_soup_error(ajax_soup)
            raise ScrapeError(422, "Couldn't find download button") from None

        if uploaded_date := ajax_soup.select_one(_SELECTOR.FILE_UPLOAD_DATE):
            scrape_item.possible_datetime = self.parse_date(uploaded_date.text.strip(), "%d/%m/%Y %H:%M:%S")

        if ajax_title := ajax_soup.select_one(_SELECTOR.FILE_NAME):
            filename = ajax_title.get_text(strip=True)
        else:
            filename = page_title.strip()

        filename, ext = self.get_filename_and_ext(filename or link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    def iter_files(self, scrape_item: ScrapeItem, soup: BeautifulSoup, *, iter_subfolders: bool = True) -> list[str]:
        """Proccess all the files in this folder. Optionally process subfolders

        Returns a list with the `folder_id` of every subfolder"""
        folder_ids = []
        for item in soup.select(_SELECTOR.FOLDER_ITEM):
            if folder_id := css.get_attr_or_none(item, "folderid"):
                folder_ids.append(folder_id)
                if not iter_subfolders:
                    continue
                link_str = css.get_attr(item, "sharing-url")
            elif css.get_attr_or_none(item, "fileid"):
                link_str = css.get_attr(item, "dtfullurl")
            else:
                continue

            link = self.parse_url(link_str)
            new_scrape_item = scrape_item.create_child(link)
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.add_children()
        return folder_ids

    async def get_soup_from_ajax(
        self, data: dict, scrape_item: ScrapeItem, is_file: bool = False
    ) -> tuple[BeautifulSoup, str]:
        """Returns soup and page title as a tuple"""

        async def get_ajax_info() -> tuple[BeautifulSoup, str]:
            async with self.request_limiter:
                json_resp: dict = await self.client.post_data(self.DOMAIN, ajax_url, data=data)
            html: str = json_resp["html"]
            return BeautifulSoup(html.replace("\\", ""), "html.parser"), json_resp["page_title"]

        password = scrape_item.url.query.get("password", "")
        ajax_url = self.files_api_url if is_file else self.folders_api_url
        ajax_soup, ajax_title = await get_ajax_info()
        if is_password_protected(ajax_soup):
            if not password:
                raise PasswordProtectedError
            try:
                node_id = data.get("nodeId") or ajax_soup.select(_SELECTOR.FOLDER_ID)[0]["value"]
            except (IndexError, AttributeError):
                check_soup_error(ajax_soup)
                raise ScrapeError(422, message="nodeId not found") from None

            # Make a request with the password. Access to the file/folder will be stored in cookies
            pw_data = {"folderPassword": password, "folderId": node_id, "submitme": 1}
            async with self.request_limiter:
                json_resp: dict = await self.client.post_data(self.DOMAIN, self.folder_password_api_url, data=pw_data)
            if not json_resp.get("success"):
                raise PasswordProtectedError(message="Incorrect password")

            ajax_soup, ajax_title = await get_ajax_info()

        return ajax_soup, ajax_title


def is_password_protected(soup: BeautifulSoup) -> bool:
    html = soup.get_text()
    return any(text in html for text in ("Enter File Password", "Password Required"))


def check_soup_error(soup: BeautifulSoup) -> None:
    html = soup.get_text()
    for code, errors in SOUP_ERRORS.items():
        for text in errors:
            if text in html:
                raise ScrapeError(code)
