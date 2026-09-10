from __future__ import annotations

from typing import ClassVar, Literal, NotRequired, TypedDict

from typing_extensions import ReadOnly

from cyberdrop_dl import aio
from cyberdrop_dl.crawlers.crawler import API, Crawler, SupportedPaths
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.url_objects import AbsoluteHttpURL, ScrapeItem
from cyberdrop_dl.utils.errors import error_handling_wrapper


class ClonrCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Clone": "/<clone_id>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://clonr.co")
    DOMAIN: ClassVar[str] = "clonr"

    def __post_init__(self) -> None:
        self.api: ClonrAPI = ClonrAPI.from_crawler(self)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case [clone_id]:
                await self.clone(scrape_item, clone_id)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def clone(self, scrape_item: ScrapeItem, clone_id: str) -> None:
        clone = await self.api.clone(clone_id)
        files: list[File] = clone.pop("files", [])  # pyright: ignore[reportAssignmentType]
        self.create_eager_task(self.write_metadata(scrape_item, clone_id, clone))

        if self.config.crawlers.clonr.use_source and (url := clone.get("source_url")):
            self.handle_external_links(scrape_item.create_child(self.parse_url(url)))
            return

        if clone["cache_state"] != "completed":
            pending = sum(1 for f in files if f["state"] != "done")
            if pending == len(files):
                raise ScrapeError(204, "Clone has no files imported")

            self.log.warning(
                "Clone %s is incomplete, %s/%s files are still pending import",
                clone_id,
                f"{pending:,}",
                f"{len(files):,}",
            )

        scrape_item.setup_as_album(self.create_title(clone["name"], clone_id), album_id=clone_id)

        if self.config.crawlers.clonr.zip and (url := clone.get("zip_url")):
            await self.direct_file(scrape_item, self.parse_url(url))
            return

        sleep = aio.periodic_sleep(10)
        async with self.new_task_group() as tg:
            for file in files:
                tg.create_eager_task(self._file(scrape_item, file))
                scrape_item.add_children()
                await sleep()

    @error_handling_wrapper
    async def _file(self, scrape_item: ScrapeItem, file: File) -> None:
        if file["state"] != "done":
            self.log.warning("Ignoring file [%s] '%s'", file["state"], file["name"])
            return

        src = self.parse_url(file["url"])
        filename, ext = self.get_filename_and_ext(file["name"])
        scrape_item.uploaded_at = file["modified_at"]
        await self.handle_file(
            src,
            scrape_item,
            file["name"],
            ext,
            custom_filename=filename,
            metadata=file,
            thumbnail=file.get("poster"),
        )


class File(TypedDict):
    name: str
    state: ReadOnly[Literal["pending", "done"]]
    modified_at: int
    poster: str | None
    preview: str | None
    url: str


class Clone(TypedDict):
    id: str
    name: str
    cache_state: str
    source_url: NotRequired[str]
    total_files: int
    zip_url: NotRequired[str]
    files: list[File]


class ClonrAPI(API):
    ENTRYPOINT: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://clonr.co/api")

    async def clone(self, clone_id: str) -> Clone:
        url = self.ENTRYPOINT / "clone" / clone_id
        return await self.request_json(url)
