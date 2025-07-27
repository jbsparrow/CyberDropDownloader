from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias

from rich.table import Table

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence

    from cyberdrop_dl.crawlers.crawler import Crawler, CrawlerInfo


SUPPORTED_SITES_URL = "https://script-ware.gitbook.io/cyberdrop-dl/reference/supported-websites"
MarkdownRowDict: TypeAlias = dict[str, str]


def get_crawlers_info_as_rich_table() -> Table:
    caption = f"Visit {SUPPORTED_SITES_URL} for a details about supported paths"
    table = Table(title="Cyberdrop-DL Supported Sites", caption=caption)
    columns, rows = _get_crawlers_info_cols_and_rows()

    for column in columns[0:3]:
        table.add_column(column, no_wrap=True)

    for row_values in rows:
        table.add_row(*row_values[0:3])

    return table


def get_crawlers_info_as_markdown_table() -> str:
    from py_markdown_table.markdown_table import markdown_table

    rows = _make_html_rows()
    table = markdown_table(rows).set_params("markdown", padding_width=10, padding_weight="centerright", quote=False)
    return table.get_markdown()


def _make_html_rows() -> list[MarkdownRowDict]:
    columns, rows = _get_crawlers_info_cols_and_rows()
    html_rows: list[MarkdownRowDict] = []
    for row in rows:
        html_row_values = [r.replace("\n", "<br>") for r in row]
        html_row_dict = MarkdownRowDict(zip(columns, html_row_values, strict=True))
        html_rows.append(html_row_dict)
    return html_rows


def _get_crawlers_info_cols_and_rows() -> tuple[list[str], Generator[tuple[str, ...]]]:
    from cyberdrop_dl.scraper.scrape_mapper import get_unique_crawlers

    def make_colunm(field_name: str) -> str:
        return field_name.replace("_", " ").title().replace("Url", "URL")

    crawlers = get_unique_crawlers()
    columns = [make_colunm(f) for f in crawlers[0].INFO._fields]
    return columns, _gen_crawlers_info_rows(crawlers)


def _gen_crawlers_info_rows(crawlers: Sequence[Crawler]) -> Generator[tuple[str, ...]]:
    info_gen = (crawler.INFO for crawler in crawlers if not crawler.IS_FALLBACK_GENERIC)
    for info in sorted(info_gen, key=lambda x: x.site.casefold()):
        yield _get_row_values(info)


def _join_supported_paths(paths: tuple[str, ...] | list[str], quote_char: str = "`") -> str:
    joined = "\n".join([f" - {quote_char}{p}{quote_char}" for p in paths])
    return f"{joined}\n"


def _get_supported_paths_and_notes(crawler_info: CrawlerInfo) -> tuple[str, str]:
    supported_paths: str = ""
    notes: str = ""

    for name, paths in crawler_info.supported_paths.items():
        if "direct link" in name.casefold() and (not paths or paths == ("",)):
            supported_paths += "Direct Links\n"
            continue
        if isinstance(paths, str):
            paths = [paths]
        if "*note*" in name.casefold():
            notes += _join_supported_paths(paths, "")
            continue

        supported_paths += f"{name}: \n{_join_supported_paths(paths)}"

    return supported_paths, notes


def _get_row_values(crawler_info: CrawlerInfo) -> tuple[str, ...]:
    supported_paths, notes = _get_supported_paths_and_notes(crawler_info)
    if notes:
        supported_paths = f"{supported_paths}\n\n**NOTES**\n{notes}"
    supported_domains = "\n".join(crawler_info.supported_domains)
    row_values = crawler_info.site, str(crawler_info.primary_url).removesuffix("/"), supported_domains, supported_paths
    return row_values
