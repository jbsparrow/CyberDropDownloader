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
from cyberdrop_dl.utils.dataclasses.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class CyberfileCrawler(Crawler):
    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "cyberfile", "Cyberfile")
        self.api_files = URL("https://cyberfile.me/account/ajax/load_files")
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
            raise ScrapeError(404, "Folder has been deleted", origin=scrape_item)

        script_func = soup.select('div[class*="page-container"] script')[-1].text
        script_func = script_func.split("loadImages(")[-1]
        script_func = script_func.split(";")[0]
        nodeId = int(script_func.split(",")[1].replace("'", ""))
        scrape_item.album_id = scrape_item.url.parts[2]
        scrape_item.part_of_album = True
        password = scrape_item.url.query.get("password", "")
        # Do not reset if nested folder
        if scrape_item.type != FILE_HOST_ALBUM:
            scrape_item.type = FILE_HOST_ALBUM
            scrape_item.children = scrape_item.children_limit = 0

            with contextlib.suppress(IndexError, TypeError):
                scrape_item.children_limit = self.manager.config_manager.settings_data["Download_Options"][
                    "maximum_number_of_children"
                ][scrape_item.type]

        page = 1
        while True:
            data = {"pageType": "folder", "nodeId": nodeId, "pageStart": page, "perPage": 0, "filterOrderBy": ""}
            async with self.request_limiter:
                ajax_dict: dict = await self.client.post_data(
                    self.domain,
                    self.api_files,
                    data=data,
                    origin=scrape_item,
                )
                if "Password Required" in ajax_dict["html"]:
                    password_data = {"folderPassword": password, "folderId": nodeId, "submitme": 1}
                    password_response: dict = await self.client.post_data(
                        self.domain,
                        self.api_password_process,
                        data=password_data,
                        origin=scrape_item,
                    )
                    if not password_response.get("success"):
                        raise PasswordProtectedError(origin=scrape_item)
                    ajax_dict: dict = await self.client.post_data(
                        self.domain,
                        self.api_files,
                        data=data,
                        origin=scrape_item,
                    )

                ajax_soup = BeautifulSoup(ajax_dict["html"].replace("\\", ""), "html.parser")

            title = self.create_title(ajax_dict["page_title"], scrape_item.album_id, None)
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
                if link:
                    new_scrape_item = self.create_scrape_item(
                        scrape_item,
                        link,
                        title,
                        True,
                        add_parent=scrape_item.url,
                    )
                    self.manager.task_group.create_task(self.run(new_scrape_item))
                else:
                    log(f"Couldn't find folder or file id for {scrape_item.url} element", 30)
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
                scrape_item.children_limit = self.manager.config_manager.settings_data["Download_Options"][
                    "maximum_number_of_children"
                ][scrape_item.type]

        page = 1
        while True:
            data = {
                "pageType": "nonaccountshared",
                "nodeId": node_id,
                "pageStart": page,
                "perPage": 0,
                "filterOrderBy": "",
            }
            async with self.request_limiter:
                ajax_dict = await self.client.post_data("cyberfile", self.api_files, data=data, origin=scrape_item)
                ajax_soup = BeautifulSoup(ajax_dict["html"].replace("\\", ""), "html.parser")
            title = self.create_title(ajax_dict["page_title"], scrape_item.url.parts[2], None)
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

                if link:
                    new_scrape_item = self.create_scrape_item(
                        scrape_item,
                        link,
                        title,
                        True,
                        add_parent=scrape_item.url,
                    )
                    self.manager.task_group.create_task(self.run(new_scrape_item))

                else:
                    log(f"Couldn't find folder or file id for {scrape_item.url} element", 30)
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
        password = scrape_item.url.query.get("password", "")
        scrape_item.url = scrape_item.url.with_query(None)
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)
            if "Enter File Password" in soup.text:
                password_data = {"filePassword": password, "submitted": 1}
                soup = BeautifulSoup(
                    await self.client.post_data(
                        self.domain,
                        scrape_item.url,
                        data=password_data,
                        raw=True,
                        origin=scrape_item,
                    ),
                )
                if "File password is invalid" in soup.text:
                    raise PasswordProtectedError(origin=scrape_item)

        script_funcs = soup.select("script")
        for script in script_funcs:
            script_text = script.text
            if script_text and "showFileInformation" in script_text:
                contentId_a = script_text.split("showFileInformation(")
                contentId_a = next(x for x in contentId_a if x[0].isdigit())
                contentId_b = contentId_a.split(");")[0]
                contentId = int(contentId_b)
                await self.handle_content_id(scrape_item, contentId)
                return

    @error_handling_wrapper
    async def handle_content_id(self, scrape_item: ScrapeItem, content_id: int) -> None:
        """Scrapes a file using the content id."""
        data = {"u": content_id}
        async with self.request_limiter:
            ajax_dict = await self.client.post_data(self.domain, self.api_details, data=data, origin=scrape_item)
            ajax_soup = BeautifulSoup(ajax_dict["html"].replace("\\", ""), "html.parser")

        if "albumPasswordModel" in ajax_dict["html"]:
            raise PasswordProtectedError(origin=scrape_item)

        file_menu = ajax_soup.select_one('ul[class="dropdown-menu dropdown-info account-dropdown-resize-menu"] li a')
        file_button = ajax_soup.select_one('div[class="btn-group responsiveMobileMargin"] button')
        try:
            html_download_text = file_menu.get("onclick") if file_menu else file_button.get("onclick")
        except AttributeError:
            log(f"Couldn't find download button for {scrape_item.url}", 30)
            raise ScrapeError(422, "Couldn't find download button", origin=scrape_item) from None
        link = URL(html_download_text.split("'")[1])

        file_detail_table = ajax_soup.select('table[class="table table-bordered table-striped"]')[-1]
        uploaded_row = file_detail_table.select("tr")[-2]
        uploaded_date = uploaded_row.select_one("td[class=responsiveTable]").text.strip()
        uploaded_date = self.parse_datetime(uploaded_date)
        scrape_item.possible_datetime = uploaded_date

        filename, ext = get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        date = datetime.datetime.strptime(date, "%d/%m/%Y %H:%M:%S")
        return calendar.timegm(date.timetuple())
