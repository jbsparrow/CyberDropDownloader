from __future__ import annotations

import asyncio
import contextlib
import itertools
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import PIL
from filedate import File
from PIL import Image
from videoprops import get_audio_properties, get_video_properties

from cyberdrop_dl.utils.constants import FILE_FORMATS
from cyberdrop_dl.utils.logger import log_with_color
from cyberdrop_dl.utils.utilities import purge_dir_tree

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


def get_file_date_in_us_ca_formats(file: Path) -> tuple[str, str]:
    file_date = File(str(file)).get()
    file_date_us = file_date["modified"].strftime("%Y-%d-%m")
    file_date_ca = file_date["modified"].strftime("%Y-%m-%d")
    return file_date_us, file_date_ca


class Sorter:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.download_dir = manager.path_manager.scan_folder or manager.path_manager.download_folder
        self.sorted_downloads = manager.path_manager.sorted_folder
        self.incrementer_format: str = manager.config_manager.settings_data.sorting.sort_incremementer_format
        self.sort_cdl_only = manager.config_manager.settings_data.sorting.sort_cdl_only
        if manager.config_manager.settings_data.download_options.skip_download_mark_completed:
            self.sort_cdl_only = False
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
        return [file for file in directory.rglob("*") if file.is_file()]

    def move_file(self, old_path: Path, new_path: Path) -> bool:
        """Moves a file to a destination folder."""
        if old_path.resolve() == new_path.resolve():
            return
        try:
            new_path.parent.mkdir(parents=True, exist_ok=True)
            old_path.rename(new_path)

        except FileExistsError:
            if old_path.stat().st_size == new_path.stat().st_size:
                old_path.unlink()
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

    def check_sorted_dir_parents(self) -> bool:
        """Checks if the sort dir a children of download dir"""
        if self.download_dir in self.sorted_downloads.parents:
            log_with_color("Sort Directory cannot be in the Download Directory", "red", 40)
            return True
        if self.download_dir == self.sorted_downloads:
            log_with_color("Sort Directory cannot be the Directory being scanned", "red", 40)
            return True
        return False

    async def sort(self) -> None:
        """Sorts the files in the download directory into their respective folders."""
        log_with_color("\nSorting Downloads: Please Wait", "cyan", 20)
        # make sort dir
        self.sorted_downloads.mkdir(parents=True, exist_ok=True)

        if self.check_sorted_dir_parents():
            return

        if not self.download_dir.is_dir():
            log_with_color("Download Directory does not exist", "red", 40)
            return

        download_folders: list[Path] = await self.get_download_folders()
        files_to_sort: dict[str, list[Path]] = {}
        with self.manager.live_manager.get_sort_live(stop=True):
            subfolders = [f for f in self.download_dir.iterdir() if f.is_dir()]
            for folder in subfolders:
                if self.sort_cdl_only and folder not in download_folders:
                    continue
                files_to_sort[folder.name] = self.get_files(folder)
        await asyncio.sleep(1)
        purge_dir_tree(self.download_dir)

    def _sort_files(self, files_to_sort: dict[str, list[Path]]) -> None:
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

    async def get_download_folders(self) -> list[Path]:
        """Gets the download folder."""
        if not self.sort_cdl_only:
            return []
        download_paths = await self.db_manager.history_table.get_unique_download_paths()
        download_paths = [Path(download_path[0]) for download_path in download_paths]
        absolute_download_paths = [
            self.download_dir.joinpath(p).resolve() for p in download_paths if p != self.download_dir
        ]
        existing_download_paths = [p for p in absolute_download_paths if self.download_dir in p.parents and p.is_dir()]
        existing_folders = set()
        for folder in existing_download_paths:
            relative_folder = folder.relative_to(self.download_dir)
            base_folder = self.download_dir / relative_folder.parts[0]
            existing_folders.add(base_folder)

        return list(existing_folders)

    def sort_audio(self, file: Path, base_name: str) -> None:
        """Sorts an audio file into the sorted audio folder."""
        self.audio_count += 1
        length = bitrate = sample_rate = "Unknown"
        with contextlib.suppress(RuntimeError, subprocess.CalledProcessError):
            props = get_audio_properties(str(file))
            length = props.get("duration", "Unknown")
            bitrate = props.get("bit_rate", "Unknown")
            sample_rate = props.get("sample_rate", "Unknown")

        if self._process_file_move(file, base_name, length=length, bitrate=bitrate, sample_rate=sample_rate):
            self.manager.progress_manager.sort_progress.increment_audio()

    def sort_image(self, file: Path, base_name: str) -> None:
        """Sorts an image file into the sorted image folder."""
        self.image_count += 1
        resolution = "Unknown"
        with contextlib.suppress(PIL.UnidentifiedImageError, PIL.Image.DecompressionBombError):  # type: ignore
            image = Image.open(file)
            width, height = image.size
            resolution = f"{width}x{height}"
            image.close()

        if self._process_file_move(file, base_name, resolution=resolution):
            self.manager.progress_manager.sort_progress.increment_image()

    def sort_video(self, file: Path, base_name: str) -> None:
        """Sorts a video file into the sorted video folder."""
        self.video_count += 1
        resolution = frames_per_sec = codec = "Unknown"

        with contextlib.suppress(RuntimeError, subprocess.CalledProcessError):
            props = get_video_properties(str(file))
            width = props.get("width")
            height = props.get("height")
            if width and height:
                resolution = f"{width}x{height}"
            frames_per_sec = props.get("avg_frame_rate", "Unknown")
            codec = props.get("codec_name", "Unknown")

        if self._process_file_move(file, base_name, resolution=resolution, fps=frames_per_sec, codec=codec):
            self.manager.progress_manager.sort_progress.increment_video()

    def sort_other(self, file: Path, base_name: str) -> None:
        """Sorts an other file into the sorted other folder."""
        self.other_count += 1
        if self._process_file_move(file, base_name):
            self.manager.progress_manager.sort_progress.increment_other()

    def _process_file_move(self, file: Path, base_name: str, **kwargs) -> None:
        parent_name = file.parent.name
        filename, ext = file.stem, file.suffix
        file_date_us, file_date_ca = get_file_date_in_us_ca_formats(file)

        new_file = Path(
            self.image_format.format(
                sort_dir=self.sorted_downloads,
                base_dir=base_name,
                parent_dir=parent_name,
                filename=filename,
                ext=ext,
                file_date_us=file_date_us,
                file_date_ca=file_date_ca,
                **kwargs,
            ),
        )

        return self.move_file(file, new_file)
