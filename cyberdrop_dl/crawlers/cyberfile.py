from __future__ import annotations

import calendar
import contextlib
import datetime
from typing import TYPE_CHECKING, ClassVar

from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.clients.errors import PasswordProtectedError, ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


SOUP_ERRORS = {
    410: ["File has been removed"],
    401: ["File is not publicly available"],
}


class CyberfileCrawler(Crawler):
    PRIMARY_BASE_DOMAINS: ClassVar[dict[str, URL]] = {
        "cyberfile": URL("https://cyberfile.me/"),
        "iceyfile": URL("https://iceyfile.com/"),
    }

    FOLDER_DOMAINS: ClassVar[dict[str, str]] = {"cyberfile": "Cyberfile", "iceyfile": "Iceyfile"}
    SUPPORTED_SITES: ClassVar[dict[str, list]] = {"cyberfile": ["cyberfile"], "iceyfile": ["iceyfile"]}
    update_unsupported = True

    def __init__(self, manager: Manager, site: str) -> None:
        super().__init__(manager, site, self.FOLDER_DOMAINS.get(site, "Cyberfile"))
        self.primary_base_domain = self.PRIMARY_BASE_DOMAINS.get(site, URL(f"https://{site}"))
        self.api_load_files = self.primary_base_domain / "account/ajax/load_files"
        self.api_details = self.primary_base_domain / "account/ajax/file_details"
        self.api_password_process = self.primary_base_domain / "ajax/folder_password_process"
        self.request_limiter = AsyncLimiter(5, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "folder" in scrape_item.url.parts:
            await self.folder(scrape_item)
        elif "shared" in scrape_item.url.parts:
            await self.shared(scrape_item)
        elif scrape_item.url.path != "/":
            await self.file(scrape_item)
        else:
            raise ValueError

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a folder."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        login = soup.select_one("form[id=form_login]")
        if login:
            raise ScrapeError(410, "Folder has been deleted", origin=scrape_item)

        script_func = soup.select('div[class*="page-container"] script')[-1].text
        script_func = script_func.split("loadImages(")[-1]
        script_func = script_func.split(";")[0]
        nodeId = int(script_func.split(",")[1].replace("'", ""))
        scrape_item.album_id = scrape_item.url.parts[2]
        scrape_item.part_of_album = True
        if scrape_item.type != FILE_HOST_ALBUM:  # Do not reset if nested folder
            scrape_item.set_type(FILE_HOST_ALBUM, self.manager)

        page = 1
        while True:
            data = {"pageType": "folder", "nodeId": nodeId, "pageStart": page, "perPage": 0, "filterOrderBy": ""}
            ajax_soup, ajax_title = await self.get_soup_from_ajax(data, scrape_item)

            title = self.create_title(ajax_title, scrape_item.album_id)
            num_pages = int(
                ajax_soup.select("a[onclick*=loadImages]")[-1].get("onclick").split(",")[2].split(")")[0].strip(),
            )

            tile_listings = ajax_soup.select("div[class=fileListing] div[class*=fileItem]")
            for tile in tile_listings:
                folder_id = tile.get("folderid")
                file_id = tile.get("fileid")
                link_str = None
                if folder_id:
                    link_str = tile.get("sharing-url")
                elif file_id:
                    link_str = tile.get("dtfullurl")
                if not link_str:
                    continue

                link = self.parse_url(link_str)
                new_scrape_item = self.create_scrape_item(scrape_item, link, title, add_parent=scrape_item.url)
                self.manager.task_group.create_task(self.run(new_scrape_item))
                scrape_item.add_children()

            page += 1
            if page > num_pages:
                break

    @error_handling_wrapper
    async def shared(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a shared folder."""
        async with self.request_limiter:
            await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        new_folders = []
        node_id = ""
        if scrape_item.type != FILE_HOST_ALBUM:  # Do not reset if nested folder
            scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        scrape_item.part_of_album = True

        page = 1
        while True:
            data = {
                "pageType": "nonaccountshared",
                "nodeId": node_id,
                "pageStart": page,
                "perPage": 0,
                "filterOrderBy": "",
            }

            ajax_soup, ajax_title = await self.get_soup_from_ajax(data, scrape_item)
            title = self.create_title(ajax_title, scrape_item.url.parts[2])
            num_pages = int(ajax_soup.select_one("input[id=rspTotalPages]").get("value"))

            tile_listings = ajax_soup.select("div[class=fileListing] div[class*=fileItem]")
            for tile in tile_listings:
                folder_id = tile.get("folderid")
                file_id = tile.get("fileid")
                link_str = None
                if folder_id:
                    new_folders.append(folder_id)
                    continue
                elif file_id:
                    link_str = tile.get("dtfullurl")
                if not link_str:
                    continue

                link = self.parse_url(link_str)
                new_scrape_item = self.create_scrape_item(scrape_item, link, title, add_parent=scrape_item.url)
                self.manager.task_group.create_task(self.run(new_scrape_item))
                scrape_item.add_children()

            page += 1
            if page > num_pages and not new_folders:
                break

            if page > num_pages and new_folders:
                node_id = str(new_folders.pop(0))
                page = 1

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a file."""

        file_id = scrape_item.url.parts[1]
        canonical_url = self.primary_base_domain / file_id
        if await self.check_complete_from_referer(canonical_url):
            return

        def get_password_info(soup: BeautifulSoup, *, raise_with_message: str | None = None) -> tuple[bool, str]:
            password = scrape_item.url.query.get("password", "")
            password_protected = False
            if "Enter File Password" in soup.text:
                password_protected = True
                if not password or raise_with_message:
                    raise PasswordProtectedError(message=raise_with_message, origin=scrape_item)
            return password_protected, password

        contentId = None
        scrape_item.url = canonical_url
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        password_protected, password = get_password_info(soup)
        if password_protected:
            form = soup.select_one('form[method="POST"]')
            post_url = form.get("action") if form else None
            if not post_url:
                msg = "Unable to parse Password Protected File details"
                raise PasswordProtectedError(message=msg, origin=scrape_item)

            data = {"filePassword": password, "submitme": 1}
            async with self.request_limiter:
                resp = await self.client.post_data(self.domain, post_url, data=data, origin=scrape_item, raw=True)
            soup = BeautifulSoup(resp)
            get_password_info(soup, raise_with_message="File password is invalid")

        script_funcs = soup.select("script")
        for script in script_funcs:
            script_text = script.text
            if script_text and "showFileInformation" in script_text:
                contentId_a = script_text.split("showFileInformation(")
                contentId_a = next(x for x in contentId_a if x[0].isdigit())
                contentId_b = contentId_a.split(");")[0]
                contentId = int(contentId_b)
                break

        if not contentId:
            check_soup_error(scrape_item, soup)
            raise ScrapeError(422, message="contentId not found", origin=scrape_item)
        await self.handle_content_id(scrape_item, contentId)

    @error_handling_wrapper
    async def handle_content_id(self, scrape_item: ScrapeItem, content_id: int) -> None:
        """Scrapes a file using the content id."""
        data = {"u": content_id}
        ajax_soup, page_title = await self.get_soup_from_ajax(data, scrape_item, file=True)
        file_menu = ajax_soup.select_one('ul[class="dropdown-menu dropdown-info account-dropdown-resize-menu"] li a')
        try:
            if file_menu:
                html_download_text = file_menu.get("onclick")
            else:
                file_button = ajax_soup.select('div[class="btn-group responsiveMobileMargin"] button')[-1]
                html_download_text = file_button.get("onclick")
        except (AttributeError, IndexError):
            check_soup_error(scrape_item, ajax_soup)
            raise ScrapeError(422, "Couldn't find download button", origin=scrape_item) from None

        link_str = html_download_text.split("'")[1].strip().removesuffix("'")
        link = self.parse_url(link_str)
        file_detail_table = ajax_soup.select('table[class="table table-bordered table-striped"]')[-1]
        uploaded_row = file_detail_table.select("tr")[-2]
        uploaded_date = uploaded_row.select_one("td[class=responsiveTable]").text.strip()
        uploaded_date = self.parse_datetime(uploaded_date)
        ajax_title = None
        with contextlib.suppress(AttributeError):
            ajax_title = ajax_soup.select_one("div.image-name-title").text
        scrape_item.possible_datetime = uploaded_date
        filename, ext = self.get_filename_and_ext(page_title or ajax_title or link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        parsed_date = datetime.datetime.strptime(date, "%d/%m/%Y %H:%M:%S")
        return calendar.timegm(parsed_date.timetuple())

    async def get_soup_from_ajax(
        self, data: dict, scrape_item: ScrapeItem, file: bool = False
    ) -> tuple[BeautifulSoup, str]:
        password = scrape_item.url.query.get("password", "")
        async with self.request_limiter:
            final_entrypoint = self.api_details if file else self.api_load_files
            ajax_dict: dict = await self.client.post_data(self.domain, final_entrypoint, data=data, origin=scrape_item)

        ajax_soup = BeautifulSoup(ajax_dict["html"].replace("\\", ""), "html.parser")

        if "Password Required" in ajax_dict["html"]:
            if not password:
                raise PasswordProtectedError(origin=scrape_item)

            soup_nodeId = ajax_soup.select_one("#folderId")
            # override if data has it
            nodeId = data.get("nodeId", soup_nodeId.get("value"))
            if not nodeId:
                check_soup_error(scrape_item, ajax_soup)
                raise ScrapeError(422, message="nodeId not found", origin=scrape_item) from None

            async with self.request_limiter:
                password_data = {"folderPassword": password, "folderId": nodeId, "submitme": 1}
                password_response: dict = await self.client.post_data(
                    self.domain,
                    self.api_password_process,
                    data=password_data,
                    origin=scrape_item,
                )
                if not password_response.get("success"):
                    raise PasswordProtectedError(message="Incorrect password", origin=scrape_item)

                ajax_dict: dict = await self.client.post_data(
                    self.domain,
                    final_entrypoint,
                    data=data,
                    origin=scrape_item,
                )
                ajax_soup = BeautifulSoup(ajax_dict["html"].replace("\\", ""), "html.parser")

        return ajax_soup, ajax_dict["page_title"]


def check_soup_error(scrape_item: ScrapeItem, soup: BeautifulSoup) -> None:
    soup_text = str(soup)
    for code, errors in SOUP_ERRORS.items():
        for text in errors:
            if text in soup_text:
                raise ScrapeError(code, origin=scrape_item)
