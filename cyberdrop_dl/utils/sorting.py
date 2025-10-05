from __future__ import annotations

import asyncio
import itertools
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from subprocess import CalledProcessError
from typing import TYPE_CHECKING

import PIL
from PIL import Image
from videoprops import get_audio_properties, get_video_properties

from cyberdrop_dl.constants import FILE_FORMATS
from cyberdrop_dl.utils import strings
from cyberdrop_dl.utils.logger import log, log_with_color
from cyberdrop_dl.utils.utilities import purge_dir_tree

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cyberdrop_dl.managers.manager import Manager


async def get_modified_date(file: Path) -> datetime:
    stat = await asyncio.to_thread(file.stat)
    return datetime.fromtimestamp(stat.st_mtime).replace(microsecond=0)


class Sorter:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.download_folder = manager.path_manager.scan_folder or manager.path_manager.download_folder
        self.sorted_folder = manager.path_manager.sorted_folder
        self.incrementer_format: str = manager.config_manager.settings_data.sorting.sort_incrementer_format
        self.db_manager = manager.db_manager

        settings = manager.config_manager.settings_data.sorting
        self.audio_format: str | None = settings.sorted_audio
        self.image_format: str | None = settings.sorted_image
        self.video_format: str | None = settings.sorted_video
        self.other_format: str | None = settings.sorted_other

    async def _get_files(self, directory: Path) -> AsyncGenerator[Path]:
        """Finds all files in a directory and returns them in a list."""

        def resolve_if_file(path: Path) -> Path | None:
            if path.is_file():
                return path.resolve()

        for file in directory.rglob("*"):
            if file := await asyncio.to_thread(resolve_if_file, file):
                yield file

    def _move_file(self, old_path: Path, new_path: Path) -> bool:
        """Moves a file to a destination folder."""
        if new_path.is_symlink():
            new_path = new_path.resolve()
        if old_path == new_path:
            return True

        new_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            old_path.rename(new_path)
        except FileExistsError:
            if old_path.stat().st_size == new_path.stat().st_size:
                old_path.unlink()
                return True
            for auto_index in itertools.count(1):
                new_filename = f"{new_path.stem}{self.incrementer_format.format(i=auto_index)}{new_path.suffix}"
                possible_new_path = new_path.parent / new_filename
                try:
                    old_path.rename(possible_new_path)
                    break
                except FileExistsError:
                    continue
        except OSError:
            return False

        return True

    async def run(self) -> None:
        """Sorts the files in the download directory into their respective folders."""
        if not await asyncio.to_thread(self.download_folder.is_dir):
            log_with_color(f"Download directory ({self.download_folder}) does not exist", "red", 40)
            return

        log_with_color("\nSorting downloads, please wait", "cyan", 20)
        await asyncio.to_thread(self.sorted_folder.mkdir, parents=True, exist_ok=True)

        files_to_sort: dict[str, list[Path]] = {}

        with self.manager.live_manager.get_sort_live(stop=True):
            for subfolder in self.download_folder.iterdir():
                if not await asyncio.to_thread(subfolder.is_dir):
                    continue
                files_to_sort[subfolder.name] = [file async for file in self._get_files(subfolder)]
            await self._sort_files(files_to_sort)
            log_with_color("DONE!", "green", 20)

        purge_dir_tree(self.download_folder)

    async def _sort_files(self, files_to_sort: dict[str, list[Path]]) -> None:
        queue_length = len(files_to_sort)
        self.manager.progress_manager.sort_progress.set_queue_length(queue_length)

        for folder_name, files in files_to_sort.items():
            task_id = self.manager.progress_manager.sort_progress.add_task(folder_name, len(files))

            for file in files:
                ext = file.suffix.lower()

                if ext in (".cdl_hls", ".cdl_hsl", ".part"):
                    continue
                if ext in FILE_FORMATS["Audio"]:
                    await self.sort_audio(file, folder_name)
                elif ext in FILE_FORMATS["Images"]:
                    await self.sort_image(file, folder_name)
                elif ext in FILE_FORMATS["Videos"]:
                    await self.sort_video(file, folder_name)
                else:
                    await self.sort_other(file, folder_name)

                self.manager.progress_manager.sort_progress.advance_folder(task_id)

            self.manager.progress_manager.sort_progress.remove_task(task_id)
            queue_length -= 1
            self.manager.progress_manager.sort_progress.set_queue_length(queue_length)

    async def sort_audio(self, file: Path, base_name: str) -> None:
        """Sorts an audio file into the sorted audio folder."""
        if not self.audio_format:
            return
        bitrate = duration = sample_rate = None
        try:
            props: dict = get_audio_properties(str(file))
            duration = int(float(props.get("duration", 0))) or None
            bitrate = int(float(props.get("bit_rate", 0))) or None
            sample_rate = int(float(props.get("sample_rate", 0))) or None
        except (RuntimeError, CalledProcessError):
            log(f"Unable to get audio properties of '{file}'")

        if await self._process_file_move(
            file,
            base_name,
            self.audio_format,
            bitrate=bitrate,
            duration=duration,
            length=duration,
            sample_rate=sample_rate,
        ):
            self.manager.progress_manager.sort_progress.increment_audio()

    async def sort_image(self, file: Path, base_name: str) -> None:
        """Sorts an image file into the sorted image folder."""
        if not self.image_format:
            return
        height = resolution = width = None
        try:
            with Image.open(file) as image:
                width, height = image.size
                resolution = f"{width}x{height}"
        except (PIL.UnidentifiedImageError, PIL.Image.DecompressionBombError):  # type: ignore
            log(f"Unable to get some image properties of '{file}'")

        if await self._process_file_move(
            file,
            base_name,
            self.image_format,
            height=height,
            resolution=resolution,
            width=width,
        ):
            self.manager.progress_manager.sort_progress.increment_image()

    async def sort_video(self, file: Path, base_name: str) -> None:
        """Sorts a video file into the sorted video folder."""
        if not self.video_format:
            return

        codec = duration = fps = height = resolution = width = None

        try:
            props: dict = get_video_properties(str(file))
            width = int(float(props.get("width", 0))) or None
            height = int(float(props.get("height", 0))) or None
            if width and height:
                resolution = f"{width}x{height}"

            codec: str | None = props.get("codec_name")
            duration = int(float(props.get("duration", 0))) or None
            fps = (
                float(Fraction(props.get("avg_frame_rate", 0)))
                if str(props.get("avg_frame_rate", 0)) not in {"0/0", "0"}
                else None
            )
        except (RuntimeError, CalledProcessError):
            log(f"Unable to get some video properties of '{file}'")

        if fps is not None:
            fps = str(int(fps)) if fps.is_integer() else f"{fps:.2f}"

        if await self._process_file_move(
            file,
            base_name,
            self.video_format,
            codec=codec,
            duration=duration,
            fps=fps,
            height=height,
            resolution=resolution,
            width=width,
        ):
            self.manager.progress_manager.sort_progress.increment_video()

    async def sort_other(self, file: Path, base_name: str) -> None:
        """Sorts an other file into the sorted other folder."""
        if not self.other_format:
            return
        if await self._process_file_move(file, base_name, self.other_format):
            self.manager.progress_manager.sort_progress.increment_other()

    async def _process_file_move(self, file: Path, base_name: str, format_str: str, **kwargs) -> bool:
        file_date = await get_modified_date(file)
        file_date_us = file_date.strftime("%Y-%d-%m")
        file_date_iso = file_date.strftime("%Y-%m-%d")

        duration = kwargs.get("duration") or kwargs.get("length")
        if duration is not None:
            kwargs["duration"] = kwargs["length"] = duration

        file_path, _ = strings.safe_format(
            format_str,
            base_dir=base_name,
            ext=file.suffix,
            file_date=file_date,
            file_date_iso=file_date_iso,
            file_date_us=file_date_us,
            filename=file.stem,
            parent_dir=file.parent.name,
            sort_dir=self.sorted_folder,
            **kwargs,
        )

        new_file = Path(file_path)
        return self._move_file(file, new_file)
