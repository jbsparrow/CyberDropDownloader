# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "alive-progress",
# ]
# ///
import argparse
from pathlib import Path

from alive_progress import alive_it  # type: ignore

LEVELS_TO_INCLUDE = {"WARNING", "ERROR", "CRITICAL"}


def filter_log_file(log_file: Path, output_file: Path) -> None:
    print(f"Filtering: {log_file.resolve()}")  # noqa: T201
    log_content = log_file.read_text(encoding="utf8")
    log_lines = log_content.splitlines()
    lines_to_keep = []
    last_level = None
    for line in alive_it(log_lines):
        level = line[20:29].strip()
        if level:
            last_level = level
            if level in LEVELS_TO_INCLUDE:
                lines_to_keep.append(line)
        elif last_level in LEVELS_TO_INCLUDE:
            lines_to_keep.append(line)

    output_file.unlink(missing_ok=True)
    output_file.write_text("\n".join(lines_to_keep), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Filter a log file, keeping WARNING, ERROR and CRITICAL log messages")
    parser.add_argument("input_file", help="Path to the input log file", type=Path)
    parser.add_argument("output_file", help="Path to the output log file", type=Path)
    args = parser.parse_args()
    filter_log_file(args.input_file, args.output_file)
