from __future__ import annotations

import calendar
import contextlib
import datetime
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.clients.errors import MaxChildrenError, PasswordProtectedError, ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class CyberfileCrawler(Crawler):
    primary_base_domain = URL("https://cyberfile.me/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "cyberfile", "Cyberfile")
        self.api_load_files = URL("https://cyberfile.me/account/ajax/load_files")
        self.api_details = URL("https://cyberfile.me/account/ajax/file_details")
        self.api_password_process = URL("https://cyberfile.me/ajax/folder_password_process")
        self.request_limiter = AsyncLimiter(5, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        task_id = self.scraping_progress.add_task(scrape_item.url)

        if "folder" in scrape_item.url.parts:
            await self.folder(scrape_item)
        elif "shared" in scrape_item.url.parts:
            await self.shared(scrape_item)
        else:
            await self.file(scrape_item)

        self.scraping_progress.remove_task(task_id)

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
        # Do not reset if nested folder
        if scrape_item.type != FILE_HOST_ALBUM:
            scrape_item.type = FILE_HOST_ALBUM
            scrape_item.children = scrape_item.children_limit = 0

            with contextlib.suppress(IndexError, TypeError):
                scrape_item.children_limit = (
                    self.manager.config_manager.settings_data.download_options.maximum_number_of_children[
                        scrape_item.type
                    ]
                )

        page = 1
        while True:
            data = {"pageType": "folder", "nodeId": nodeId, "pageStart": page, "perPage": 0, "filterOrderBy": ""}
            ajax_soup, ajax_title = await self.get_soup_from_ajax(data, scrape_item)

            title = self.create_title(ajax_title, scrape_item.album_id, None)
            num_pages = int(
                ajax_soup.select("a[onclick*=loadImages]")[-1].get("onclick").split(",")[2].split(")")[0].strip(),
            )

            tile_listings = ajax_soup.select("div[class=fileListing] div[class*=fileItem]")
            for tile in tile_listings:
                folder_id = tile.get("folderid")
                file_id = tile.get("fileid")
                link = None
                if folder_id:
                    link = URL(tile.get("sharing-url"))
                elif file_id:
                    link = URL(tile.get("dtfullurl"))
                if not link:
                    continue

                new_scrape_item = self.create_scrape_item(
                    scrape_item,
                    link,
                    title,
                    True,
                    add_parent=scrape_item.url,
                )
                self.manager.task_group.create_task(self.run(new_scrape_item))

                scrape_item.children += 1
                if scrape_item.children_limit and scrape_item.children >= scrape_item.children_limit:
                    raise MaxChildrenError(origin=scrape_item)

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
        # Do not reset if nested folder
        if scrape_item.type != FILE_HOST_ALBUM:
            scrape_item.type = FILE_HOST_ALBUM
            scrape_item.children = scrape_item.children_limit = 0

            with contextlib.suppress(IndexError, TypeError):
                scrape_item.children_limit = (
                    self.manager.config_manager.settings_data.download_options.maximum_number_of_children[
                        scrape_item.type
                    ]
                )

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
            title = self.create_title(ajax_title, scrape_item.url.parts[2], None)
            num_pages = int(ajax_soup.select_one("input[id=rspTotalPages]").get("value"))

            tile_listings = ajax_soup.select("div[class=fileListing] div[class*=fileItem]")
            for tile in tile_listings:
                folder_id = tile.get("folderid")
                file_id = tile.get("fileid")
                link = None
                if folder_id:
                    new_folders.append(folder_id)
                    continue
                if file_id:
                    link = URL(tile.get("dtfullurl"))
                if not link:
                    continue

                new_scrape_item = self.create_scrape_item(
                    scrape_item,
                    link,
                    title,
                    True,
                    add_parent=scrape_item.url,
                )
                self.manager.task_group.create_task(self.run(new_scrape_item))

                scrape_item.children += 1
                if scrape_item.children_limit and scrape_item.children >= scrape_item.children_limit:
                    raise MaxChildrenError(origin=scrape_item)

            page += 1
            if page > num_pages and not new_folders:
                break

            if page > num_pages and new_folders:
                node_id = str(new_folders.pop(0))
                page = 1

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a file."""

        def get_password_info(soup: BeautifulSoup, *, raise_with_message: str | None = None) -> tuple[bool, str]:
            password = scrape_item.url.query.get("password", "")
            password_protected = False
            if "Enter File Password" in soup.text:
                password_protected = True
                if not password or raise_with_message:
                    raise PasswordProtectedError(message=raise_with_message, origin=scrape_item)
            return password_protected, password

        contentId = None
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
            raise ScrapeError(422, message="contentId not found", origin=scrape_item)
        await self.handle_content_id(scrape_item, contentId)

    @error_handling_wrapper
    async def handle_content_id(self, scrape_item: ScrapeItem, content_id: int) -> None:
        """Scrapes a file using the content id."""
        data = {"u": content_id}
        ajax_soup, _ = await self.get_soup_from_ajax(data, scrape_item, file=True)
        file_menu = ajax_soup.select_one('ul[class="dropdown-menu dropdown-info account-dropdown-resize-menu"] li a')
        file_button = ajax_soup.select_one('div[class="btn-group responsiveMobileMargin"] button')
        try:
            html_download_text = file_menu.get("onclick") if file_menu else file_button.get("onclick")
        except AttributeError:
            raise ScrapeError(422, "Couldn't find download button", origin=scrape_item) from None

        link = URL(html_download_text.split("'")[1])
        file_detail_table = ajax_soup.select('table[class="table table-bordered table-striped"]')[-1]
        uploaded_row = file_detail_table.select("tr")[-2]
        uploaded_date = uploaded_row.select_one("td[class=responsiveTable]").text.strip()
        uploaded_date = self.parse_datetime(uploaded_date)
        scrape_item.possible_datetime = uploaded_date
        filename, ext = get_filename_and_ext(ajax_soup.title or link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        date = datetime.datetime.strptime(date, "%d/%m/%Y %H:%M:%S")
        return calendar.timegm(date.timetuple())

    async def get_soup_from_ajax(
        self, data: dict, scrape_item: ScrapeItem, file: bool = False
    ) -> tuple[BeautifulSoup, str]:
        password = scrape_item.url.query.get("password", "")
        final_entrypoint = self.api_details if file else self.api_load_files
        async with self.request_limiter:
            ajax_dict: dict = await self.client.post_data(
                self.domain,
                final_entrypoint,
                data=data,
                origin=scrape_item,
            )

        ajax_soup = BeautifulSoup(ajax_dict["html"].replace("\\", ""), "html.parser")

        if "Password Required" in ajax_dict["html"]:
            if not password:
                raise PasswordProtectedError(origin=scrape_item)

            soup_nodeId = ajax_soup.select_one("#folderId")
            # override if data has it
            nodeId = data.get("nodeId", soup_nodeId.get("value"))
            if not nodeId:
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
