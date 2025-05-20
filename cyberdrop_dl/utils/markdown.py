from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, TypeAlias

from rich import print
from rich.table import Table

from cyberdrop_dl import __version__, env

if TYPE_CHECKING:
    from cyberdrop_dl.crawlers.crawler import CrawlerInfo


RowDict: TypeAlias = dict[str, str]


def show_supported_sites() -> None:
    from cyberdrop_dl.scraper.scrape_mapper import get_unique_crawlers

    def make_colunm(field_name: str) -> str:
        return field_name.replace("_", " ").title().replace("Url", "URL")

    table = Table(title="Cyberdrop-DL Supported Sites")

    html_rows: list[RowDict] = []
    crawlers = get_unique_crawlers()
    columns = [make_colunm(f) for f in crawlers[0].INFO._fields]
    for column in columns:
        table.add_column(column, no_wrap=True)

    for crawler in crawlers:
        if crawler.NAME.casefold() == "generic":
            continue
        row_values = get_row_values(crawler.INFO)
        table.add_row(*row_values)
        html_row_values = [r.replace("\n", "<br>") for r in row_values]
        html_row_dict = RowDict(zip(columns, html_row_values, strict=True))
        html_rows.append(html_row_dict)

    print(table)
    write_supported_sites_markdown(html_rows)


def get_row_values(crawler_info: CrawlerInfo) -> tuple[str, ...]:
    supported_paths: str = ""

    for name, paths in crawler_info.supported_paths.items():
        if isinstance(paths, str):
            paths = [paths]
        joined_paths = "\n".join([f" - `{p}`" for p in paths])
        value = f"{name}: \n{joined_paths}"
        supported_paths += value + "\n"

    supported_domains = "\n".join(crawler_info.supported_domains)
    row_values = crawler_info.site, str(crawler_info.primary_url), supported_domains, supported_paths
    return row_values


def write_supported_sites_markdown(rows: list[RowDict]) -> None:
    if not env.RUNNING_IN_IDE:
        return

    try:
        from py_markdown_table.markdown_table import markdown_table
    except ImportError:
        return

    table = markdown_table(rows)
    markdown = table.set_params("markdown", padding_width=10, padding_weight="centerright", quote=False).get_markdown()
    title = "# Supported sites"
    header = f"{title}\n\nList of sites supported by cyberdrop-dl-patched as of version {__version__}\n\n"
    full_table = header + markdown + "\n"
    root = Path(__file__).parents[2]
    # repo_file_path = root / "supported_sites.md"
    # repo_file_path.write_text(full_table)
    wiki_file_path = root / "docs/reference/supported-websites.md"
    wiki_file_content = wiki_file_path.read_text()

    end = "<!-- END_SUPPORTED_SITES-->"
    content_before, _, rest = wiki_file_content.partition(title)
    _, _, content_after = rest.partition(end)
    new_content = f"{content_before}{full_table}{end}{content_after}"
    wiki_file_path.write_text(new_content)
