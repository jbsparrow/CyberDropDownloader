from __future__ import annotations

import asyncio
import contextlib
import itertools
from fractions import Fraction
from pathlib import Path
from subprocess import CalledProcessError
from typing import TYPE_CHECKING

import PIL
from filedate import File
from PIL import Image
from videoprops import get_audio_properties, get_video_properties

from cyberdrop_dl.utils.constants import FILE_FORMATS
from cyberdrop_dl.utils.logger import log_with_color
from cyberdrop_dl.utils.utilities import purge_dir_tree

if TYPE_CHECKING:
    from datetime import datetime

    from cyberdrop_dl.managers.manager import Manager


def get_modified_date(file: Path) -> datetime:
    file_obj = File(str(file))
    return file_obj.modified


class Sorter:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.download_folder = manager.path_manager.scan_folder or manager.path_manager.download_folder
        self.sorted_folder = manager.path_manager.sorted_folder
        self.incrementer_format: str = manager.config_manager.settings_data.sorting.sort_incrementer_format
        self.db_manager = manager.db_manager

        self.audio_format: str = manager.config_manager.settings_data.sorting.sorted_audio
        self.image_format: str = manager.config_manager.settings_data.sorting.sorted_image
        self.video_format: str = manager.config_manager.settings_data.sorting.sorted_video
        self.other_format: str = manager.config_manager.settings_data.sorting.sorted_other

    def _get_files(self, directory: Path) -> list[Path]:
        """Finds all files in a directory and returns them in a list."""
        return [file.resolve() for file in directory.rglob("*") if file.is_file()]

    def _move_file(self, old_path: Path, new_path: Path) -> bool:
        """Moves a file to a destination folder."""
        if old_path.resolve() == new_path.resolve():
            return True
        try:
            new_path.parent.mkdir(parents=True, exist_ok=True)
            old_path.rename(new_path)

        except FileExistsError:
            if old_path.stat().st_size == new_path.stat().st_size:
                old_path.unlink()
                return True
            for auto_index in itertools.count(1):
                new_filename = f"{new_path.stem}{self.incrementer_format.format(i=auto_index)}{new_path.suffix}"
                possible_new_path = new_path.parent / new_filename
                if not possible_new_path.is_file():
                    old_path.rename(possible_new_path)
                    break
        except OSError:
            return False

        return True

    async def run(self) -> None:
        """Sorts the files in the download directory into their respective folders."""
        if not self.download_folder.is_dir():
            log_with_color(f"Download directory ({self.download_folder}) does not exists", "red", 40)
            return

        log_with_color("\nSorting downloads, please wait", "cyan", 20)
        self.sorted_folder.mkdir(parents=True, exist_ok=True)

        files_to_sort: dict[str, list[Path]] = {}
        with self.manager.live_manager.get_sort_live(stop=True):
            subfolders = [f.resolve() for f in self.download_folder.iterdir() if f.is_dir()]
            for folder in subfolders:
                files_to_sort[folder.name] = self._get_files(folder)
            await self._sort_files(files_to_sort)
            log_with_color("DONE!", "green", 40)
        purge_dir_tree(self.download_folder)

    async def _sort_files(self, files_to_sort: dict[str, list[Path]]) -> None:
        queue_length = len(files_to_sort)
        self.manager.progress_manager.sort_progress.set_queue_length(queue_length)
        for folder_name, files in files_to_sort.items():
            task_id = self.manager.progress_manager.sort_progress.add_task(folder_name, len(files))
            for file in files:
                ext = file.suffix.lower()
                if ".part" in ext:
                    continue

                if ext in FILE_FORMATS["Audio"]:
                    self.sort_audio(file, folder_name)
                elif ext in FILE_FORMATS["Images"]:
                    self.sort_image(file, folder_name)
                elif ext in FILE_FORMATS["Videos"]:
                    self.sort_video(file, folder_name)
                else:
                    self.sort_other(file, folder_name)

                self.manager.progress_manager.sort_progress.advance_folder(task_id)
            self.manager.progress_manager.sort_progress.remove_folder(task_id)
            queue_length -= 1
            self.manager.progress_manager.sort_progress.set_queue_length(queue_length)
            await asyncio.sleep(1)  # required to update the UI

    def sort_audio(self, file: Path, base_name: str) -> None:
        """Sorts an audio file into the sorted audio folder."""
        if not self.audio_format:
            return
        bitrate = duration = sample_rate = None
        with contextlib.suppress(RuntimeError, CalledProcessError):
            props: dict = get_audio_properties(str(file))
            duration = int(float(props.get("duration", 0))) or None
            bitrate = int(float(props.get("bit_rate", 0))) or None
            sample_rate = int(float(props.get("sample_rate", 0))) or None

        if self._process_file_move(
            file,
            base_name,
            self.audio_format,
            bitrate=bitrate,
            duration=duration,
            length=duration,
            sample_rate=sample_rate,
        ):
            self.manager.progress_manager.sort_progress.increment_audio()

    def sort_image(self, file: Path, base_name: str) -> None:
        """Sorts an image file into the sorted image folder."""
        if not self.image_format:
            return
        height = resolution = width = None
        with (
            contextlib.suppress(PIL.UnidentifiedImageError, PIL.Image.DecompressionBombError),
            Image.open(file) as image,
        ):  # type: ignore
            width, height = image.size
            resolution = f"{width}x{height}"

        if self._process_file_move(
            file, base_name, self.image_format, resolution=resolution, width=width, height=height
        ):
            self.manager.progress_manager.sort_progress.increment_image()

    def sort_video(self, file: Path, base_name: str) -> None:
        """Sorts a video file into the sorted video folder."""
        if not self.video_format:
            return

        codec = duration = fps = height = resolution = width = None

        with contextlib.suppress(RuntimeError, CalledProcessError):
            props: dict = get_video_properties(str(file))
            width = int(float(props.get("width", 0))) or None
            height = int(float(props.get("height", 0))) or None
            if width and height:
                resolution = f"{width}x{height}"

            codec = props.get("codec_name")
            duration = int(float(props.get("duration", 0))) or None
            fps = (
                float(Fraction(props.get("avg_frame_rate", 0)))
                if str(props.get("avg_frame_rate", 0)) not in {"0/0", "0"}
                else None
            )
            if fps:
                fps = int(fps) if fps.is_integer() else f"{fps:.2f}"

        if self._process_file_move(
            file,
            base_name,
            self.video_format,
            codec=codec,
            duration=duration,
            fps=fps,
            resolution=resolution,
            width=width,
            height=height,
        ):
            self.manager.progress_manager.sort_progress.increment_video()

    def sort_other(self, file: Path, base_name: str) -> None:
        """Sorts an other file into the sorted other folder."""
        if not self.other_format:
            return
        if self._process_file_move(file, base_name, self.other_format):
            self.manager.progress_manager.sort_progress.increment_other()

    def _process_file_move(self, file: Path, base_name: str, format_str: str, **kwargs) -> None:
        file_date = get_modified_date(file)
        file_date_us = file_date.strftime("%Y-%d-%m")
        file_date_iso = file_date.strftime("%Y-%m-%d")

        for name, value in kwargs.items():
            if value is None:
                kwargs[name] = "Unknown"

        new_file = Path(
            format_str.format(
                base_dir=base_name,
                ext=file.suffix,
                file_date_iso=file_date_iso,
                file_date_us=file_date_us,
                filename=file.stem,
                parent_dir=file.parent.name,
                sort_dir=self.sorted_folder,
                **kwargs,
            ),
        )

        return self._move_file(file, new_file)
