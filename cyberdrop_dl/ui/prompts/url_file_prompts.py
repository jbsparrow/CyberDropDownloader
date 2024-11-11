import re
from pathlib import Path

from InquirerPy import inquirer
from rich.console import Console

console = Console()


def edit_urls_prompt(file: Path, vi_mode: bool, fix_strings: bool = True) -> None:
    """Edit the URLs file."""
    console.clear()
    console.print(f"Editing URLs: {file}")
    with file.open() as f:
        existing_urls = f.read()

    result = inquirer.text(
        message="URLs:",
        multiline=True,
        default=existing_urls,
        long_instruction="Press escape and then enter to finish editing.",
        vi_mode=vi_mode,
    ).execute()

    if fix_strings:
        result = result.replace(" ", "\n")
        result = re.sub(r"(\n)+", "\n", result)

    with file.open("w") as f:
        f.write(result)
