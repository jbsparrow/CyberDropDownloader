# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "alive-progress",
# ]
# ///
import argparse
from collections.abc import Iterable
from pathlib import Path

from alive_progress import alive_it  # type: ignore

LEVELS_TO_INCLUDE = {"WARNING", "ERROR", "CRITICAL"}


def filter_log_file(log_file: Path) -> Iterable[str]:
    print(f"Filtering: {log_file.resolve()}")  # noqa: T201
    log_content = log_file.read_text(encoding="utf8")
    last_level = None
    for line in alive_it(log_content.splitlines()):
        level = line[20:29].strip()
        if level:
            last_level = level
            if level in LEVELS_TO_INCLUDE:
                yield line
        elif last_level in LEVELS_TO_INCLUDE:
            yield line


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Filter a log file, keeping WARNING, ERROR and CRITICAL log messages")
    parser.add_argument("input", help="Path to the input log file/folder", type=Path)
    parser.add_argument("output", help="Path to the output log file", type=Path)
    args = parser.parse_args()
    input_: Path = args.input
    output: Path = args.output
    if input_.is_dir():
        files = (file for file in input_.iterdir() if file.suffix == ".log")
    elif input_.is_file():
        files = (input_,)
    else:
        raise FileNotFoundError(input_)

    lines = ("\n".join(filter_log_file(file)) for file in files)
    content = "\n".join(lines)
    output.unlink(missing_ok=True)
    output.write_text(content, encoding="utf-8")
