# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "aiohttp",
#     "python-dateutil",
#     "packaging",
#     "rich",
#     "yarl",
# ]
# ///
import asyncio
import csv
import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

import aiohttp
from dateutil import parser
from packaging.version import Version
from rich import print
from rich.progress import Progress
from rich.table import Table
from yarl import URL

if TYPE_CHECKING:
    from collections.abc import Generator


class PackageInfo(NamedTuple):
    name: str
    current_version: Version
    latest_version: Version | str | None
    release_date: str | None
    update_available: bool


async def fetch_package_info(session: aiohttp.ClientSession, package: dict[str, str]) -> PackageInfo:
    name: str = package["name"]
    current_version = Version(package["version"])
    latest_version = release_date = None

    try:
        pypi_url: URL = URL("https://pypi.org/pypi/") / name / "json"
        async with session.get(pypi_url) as response:
            pypi_data: dict[str, Any] = await response.json()

        latest_version = Version(pypi_data["info"]["version"])
        release_date_str: str = pypi_data["releases"][str(latest_version)][0]["upload_time"]
        release_date = parser.isoparse(release_date_str).date().isoformat()

    except aiohttp.ClientError as e:
        latest_version = release_date = "Error fetching"
        print(f"Error fetching {name} from PyPI: {e}")

    except (KeyError, IndexError) as e:
        latest_version = release_date = "Error parsing"
        print(f"Error parsing PyPI data for {name}: {e}")

    update_available: bool = latest_version not in (None, current_version, "Error fetching", "Error parsing")

    return PackageInfo(name, current_version, latest_version, release_date, update_available)


def get_direct_dependencies() -> "Generator[str]":
    pyproject_toml = Path(__file__).parents[2] / "pyproject.toml"
    with pyproject_toml.open(encoding="utf-8") as file:
        content = file.read()
        start_index = content.index("dependencies = [") + len("dependencies = [")
        end_index = content.index("]\n", start_index)
        dependencies = content[start_index:end_index]
        for dep in dependencies.splitlines():
            name = dep.replace('"', "").strip().split(" ")[0]
            for separator in " (>=":
                name = name.split(separator)[0].strip()
            if name:
                yield name.casefold()


async def get_all_package_info() -> list[PackageInfo]:
    try:
        direct_dependencies: list[str] = list(get_direct_dependencies())
        pip_output: str = subprocess.check_output(["pip", "list", "--format", "json"], text=True)  # noqa : ASYNC221
        pip_json: list[dict[str, Any]] = json.loads(pip_output)
        installed_packages: list[dict] = [p for p in pip_json if p["name"].casefold() in direct_dependencies]
        total_packages: int = len(installed_packages)

        all_packages: list[PackageInfo] = []
        async with aiohttp.ClientSession(raise_for_status=True) as session:
            tasks = [asyncio.create_task(fetch_package_info(session, p)) for p in installed_packages]
            with Progress() as progress:
                task_id: int = progress.add_task("Getting packages information", total=total_packages)

                for future in asyncio.as_completed(tasks):
                    result: PackageInfo = await future
                    all_packages.append(result)
                    progress.update(task_id, advance=1)

        return sorted(all_packages, key=case_insensitive_sort_key)

    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")

    except json.JSONDecodeError:
        print("Error: Could not decode JSON output from pip.")

    return []


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


def case_insensitive_sort_key(item: tuple):
    return tuple(item.casefold() if isinstance(item, str) else item for item in item)


def value_to_str(item: Any) -> str:
    if item is None:
        return "N/A"
    if isinstance(item, bool):
        return "Yes" if item else "No"
    return str(item)


def save_to_csv(package_info: list[PackageInfo], file: Path = Path("package_info.csv")) -> None:
    with file.open("w", encoding="utf-8", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=PackageInfo._fields, delimiter=";")
        writer.writeheader()
        for package in package_info:
            data = package._asdict()
            writer.writerow(data)

    print(f"Package information saved to {file.resolve()}")


def print_package_info(package_info: list[PackageInfo]) -> None:
    headers = ["Package Name"] + [f.replace("_", " ").title() for f in PackageInfo._fields[1:]]
    table = Table(*headers, title="Package Information")
    for package in package_info:
        table.add_row(*map(value_to_str, package))

    print(table)


async def main() -> None:
    package_data: list[PackageInfo] = await get_all_package_info()
    save_to_csv(package_data)
    print_package_info(package_data)


if __name__ == "__main__":
    asyncio.run(main())
