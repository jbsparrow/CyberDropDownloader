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
        self.incrementer_format: str = manager.config_manager.settings_data.sorting.sort_incremementer_format
        self.sort_cdl_only = (
            manager.config_manager.settings_data.sorting.sort_cdl_only
            and not manager.config_manager.settings_data.download_options.skip_download_mark_completed
        )
        self.db_manager = manager.db_manager

        self.audio_format: str = manager.config_manager.settings_data.sorting.sorted_audio
        self.image_format: str = manager.config_manager.settings_data.sorting.sorted_image
        self.video_format: str = manager.config_manager.settings_data.sorting.sorted_video
        self.other_format: str = manager.config_manager.settings_data.sorting.sorted_other

        self.audio_count = 0
        self.image_count = 0
        self.video_count = 0
        self.other_count = 0

    def get_files(self, directory: Path) -> list[Path]:
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
                new_path = (
                    new_path.parent / f"{new_path.stem}{self.incrementer_format.format(i=auto_index)}{new_path.suffix}"
                )
                if not new_path.is_file():
                    old_path.rename(new_path)
                    break
        except OSError:
            return False

        return True

    async def sort_files(self) -> None:
        """Sorts the files in the download directory into their respective folders."""
        if not self.download_folder.is_dir():
            log_with_color("Download Directory does not exist", "red", 40)
            return

        log_with_color("\nSorting Downloads: Please Wait", "cyan", 20)
        self.sorted_folder.mkdir(parents=True, exist_ok=True)

        download_folders: set[Path] = await self.get_download_folders()
        files_to_sort: dict[str, list[Path]] = {}
        with self.manager.live_manager.get_sort_live(stop=True):
            subfolders = [f.resolve() for f in self.download_folder.iterdir() if f.is_dir()]
            for folder in subfolders:
                if self.sort_cdl_only and folder not in download_folders:
                    continue
                files_to_sort[folder.name] = self.get_files(folder)
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
            await asyncio.sleep(1)

    async def get_download_folders(self) -> set[Path]:
        """Gets the download folder."""
        if not self.sort_cdl_only:
            return []
        download_paths = await self.db_manager.history_table.get_unique_download_paths()
        download_paths = {Path(download_path[0]) for download_path in download_paths}
        absolute_download_paths = {p for p in download_paths if p.is_absolute()}
        relative_paths = download_paths - absolute_download_paths
        with contextlib.suppress(ValueError):
            for path in relative_paths:
                proper_relative_path = path.relative_to(self.download_folder)
                absolute_download_paths.add(self.download_folder.joinpath(proper_relative_path).resolve())

        existing_download_paths = {
            p for p in absolute_download_paths if self.download_folder.resolve() in p.parents and p.is_dir()
        }
        existing_folders = set()
        for folder in existing_download_paths:
            relative_folder = folder.relative_to(self.download_folder.resolve())
            base_folder = self.download_folder.resolve() / relative_folder.parts[0]
            existing_folders.add(base_folder)

        return existing_folders

    def sort_audio(self, file: Path, base_name: str) -> None:
        """Sorts an audio file into the sorted audio folder."""
        if not self.audio_format:
            return
        self.audio_count += 1
        length = bitrate = sample_rate = "Unknown"
        with contextlib.suppress(RuntimeError, CalledProcessError):
            props: dict = get_audio_properties(str(file))
            length = props.get("duration", "Unknown")
            bitrate = props.get("bit_rate", "Unknown")
            sample_rate = props.get("sample_rate", "Unknown")

        if self._process_file_move(
            file, base_name, self.audio_format, length=length, bitrate=bitrate, sample_rate=sample_rate
        ):
            self.manager.progress_manager.sort_progress.increment_audio()

    def sort_image(self, file: Path, base_name: str) -> None:
        """Sorts an image file into the sorted image folder."""
        if not self.image_format:
            return
        self.image_count += 1
        resolution = "Unknown"
        with contextlib.suppress(PIL.UnidentifiedImageError, PIL.Image.DecompressionBombError):  # type: ignore
            image = Image.open(file)
            width, height = image.size
            resolution = f"{width}x{height}"
            image.close()

        if self._process_file_move(file, base_name, self.image_format, resolution=resolution):
            self.manager.progress_manager.sort_progress.increment_image()

    def sort_video(self, file: Path, base_name: str) -> None:
        """Sorts a video file into the sorted video folder."""
        if not self.video_format:
            return
        self.video_count += 1
        codec = duration = fps = resolution = "Unknown"

        with contextlib.suppress(RuntimeError, CalledProcessError):
            props: dict = get_video_properties(str(file))
            width = props.get("width")
            height = props.get("height")
            if width and height:
                resolution = f"{width}x{height}"
            codec = props.get("codec_name", "Unknown")
            duration = int(props.get("duration", 0)) or "Unknown"
            frames_per_sec = float(Fraction(props.get("avg_frame_rate", 0)))
            if frames_per_sec:
                fps = int(frames_per_sec) if frames_per_sec.is_integer() else f"{frames_per_sec:.2f}"

        if self._process_file_move(
            file,
            base_name,
            self.video_format,
            codec=codec,
            duration=duration,
            fps=fps,
            resolution=resolution,
        ):
            self.manager.progress_manager.sort_progress.increment_video()

    def sort_other(self, file: Path, base_name: str) -> None:
        """Sorts an other file into the sorted other folder."""
        if not self.other_format:
            return
        self.other_count += 1
        if self._process_file_move(file, base_name, self.other_format):
            self.manager.progress_manager.sort_progress.increment_other()

    def _process_file_move(self, file: Path, base_name: str, format_str: str, **kwargs) -> None:
        file_date = get_modified_date(file)
        file_date_us = file_date.strftime("%Y-%d-%m")
        file_date_iso = file_date.strftime("%Y-%m-%d")

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
