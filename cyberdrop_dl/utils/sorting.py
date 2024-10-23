import asyncio
import itertools
import logging
import subprocess
from os import name as os_name
from pathlib import Path
from typing import TYPE_CHECKING

import PIL
import filedate
from PIL import Image
from videoprops import get_audio_properties, get_video_properties

from cyberdrop_dl.utils.utilities import FILE_FORMATS, log_with_color, purge_dir_tree

logger = logging.getLogger('cyberdrop_dl')

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


def get_file_date_in_us_ca_formats(file: Path) -> tuple[str, str]:
    file_date = filedate.File(str(file)).get()
    file_date_us = file_date['modified'].strftime("%Y-%d-%m")
    file_date_ca = file_date['modified'].strftime("%Y-%m-%d")
    return file_date_us, file_date_ca


class Sorter:
    def __init__(self, manager: 'Manager'):
        self.manager = manager
        self.download_dir = manager.path_manager.scan_dir if manager.path_manager.scan_dir is not None else manager.path_manager.download_dir
        self.sorted_downloads = manager.path_manager.sorted_dir
        self.incrementer_format = manager.config_manager.settings_data['Sorting']['sort_incremementer_format']
        self.sort_cdl_only = manager.config_manager.settings_data['Sorting']['sort_cdl_only']
        if manager.config_manager.settings_data['Download_Options']['skip_download_mark_completed']:
            self.sort_cdl_only = False
        self.db_manager = manager.db_manager

        self.audio_format = manager.config_manager.settings_data['Sorting']['sorted_audio']
        self.image_format = manager.config_manager.settings_data['Sorting']['sorted_image']
        self.video_format = manager.config_manager.settings_data['Sorting']['sorted_video']
        self.other_format = manager.config_manager.settings_data['Sorting']['sorted_other']

        self.audio_count = 0
        self.image_count = 0
        self.video_count = 0
        self.other_count = 0

    async def find_files_in_dir(self, directory: Path) -> list:
        """Finds all files in a directory and returns them in a list"""
        file_list = []
        for x in directory.iterdir():
            if x.is_file():
                file_list.append(x)
            elif x.is_dir():
                file_list.extend(await self.find_files_in_dir(x))
        return file_list

    async def move_cd(self, file: Path, dest: Path) -> None:
        """Moves a file to a destination folder"""
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            file.rename(dest)
        except PermissionError:
            return False
        except FileExistsError:
            if file.stat().st_size == dest.stat().st_size:
                file.unlink()
                return
            for i in itertools.count(1):
                dest_make = dest.parent / f"{dest.stem}{self.incrementer_format.format(i=i)}{dest.suffix}"
                if not dest_make.is_file():
                    break
            file.rename(dest_make)

    async def check_dir_parents(self) -> bool:
        """Checks if the sort dir is in the download dir"""
        if self.download_dir in self.sorted_downloads.parents:
            await log_with_color("Sort Directory cannot be in the Download Directory", "red", 40)
            return True
        elif self.download_dir == self.sorted_downloads:
            await log_with_color("Sort Directory cannot be the Directory being scanned", "red", 40)
            return True
        return False

    async def sort(self) -> None:
        """Sorts the files in the download directory into their respective folders"""
        await log_with_color("\nSorting Downloads: Please Wait", "cyan", 20)
        # make sort dir
        self.sorted_downloads.mkdir(parents=True, exist_ok=True)

        if await self.check_dir_parents():
            return

        if not self.download_dir.is_dir():
            await log_with_color("Download Directory does not exist", "red", 40)
            return

        download_folders = await self.get_download_folder()
        async with self.manager.live_manager.get_sort_live(stop=True):
            all_scan_folders = list(filter(lambda x: x.is_dir(), self.download_dir.iterdir()))
            queue_length = len(all_scan_folders)
            await self.manager.progress_manager.sort_progress.set_queue_length(queue_length)

            for folder in all_scan_folders:
                if self.sort_cdl_only and folder not in download_folders:
                    pass
                else:
                    files = await self.find_files_in_dir(folder)
                    # add folder to progress and set number of files
                    task_id = await self.manager.progress_manager.sort_progress.add_task(folder.name, len(files))
                    for file in files:
                        ext = file.suffix.lower()
                        if '.part' in ext:
                            continue

                        if ext in FILE_FORMATS['Audio']:
                            await self.sort_audio(file, folder.name)
                        elif ext in FILE_FORMATS['Images']:
                            await self.sort_image(file, folder.name)
                        elif ext in FILE_FORMATS['Videos']:
                            await self.sort_video(file, folder.name)
                        else:
                            await self.sort_other(file, folder.name)
                        await self.manager.progress_manager.sort_progress.advance_folder(task_id,
                                                                                        1)  # advance folder progress by one file
                    await purge_dir_tree(folder)
                queue_length -= 1
                await self.manager.progress_manager.sort_progress.set_queue_length(queue_length)  # update queue length
                await self.manager.progress_manager.sort_progress.remove_folder(task_id)  # remove folder from progress

        await asyncio.sleep(1)
        await purge_dir_tree(self.download_dir)

        clear_screen_proc = await asyncio.create_subprocess_shell('cls' if os_name == 'nt' else 'clear')
        await clear_screen_proc.wait()

    async def get_download_folder(self):
        """Gets the download folder"""
        if not self.sort_cdl_only:
            return []
        unique_download_paths = await self.db_manager.history_table.get_unique_download_paths()
        download_folders = [Path(download_path[0]) for download_path in unique_download_paths if
                            Path(download_path[0]).is_dir() and Path(download_path[0]) != self.download_dir]
        existing_folders = []
        for folder in download_folders:
            try:
                relative_folder = folder.relative_to(self.download_dir)
                base_folder = self.download_dir / relative_folder.parts[0]
            except Exception as e:
                if e.__class__ == ValueError:
                    continue
                logger.log(40,
                        f"Error: {e}\n\nfolder: {folder}\ndownload_dir: {self.download_dir}\nrelative_folder: {relative_folder}")
                raise e
            if base_folder.exists():
                existing_folders.append(base_folder)
        download_folders.extend(existing_folders)
        download_folders = list(set(download_folders))
        return download_folders

    async def sort_audio(self, file: Path, base_name: str) -> None:
        """Sorts an audio file into the sorted audio folder"""
        self.audio_count += 1

        try:
            props = get_audio_properties(str(file))
            length = str(props.get('duration', "Unknown"))
            bitrate = str(props.get('bit_rate', "Unknown"))
            sample_rate = str(props.get('sample_rate', "Unknown"))
        except (RuntimeError, subprocess.CalledProcessError):
            length = "Unknown"
            bitrate = "Unknown"
            sample_rate = "Unknown"

        parent_name = file.parent.name
        filename, ext = file.stem, file.suffix
        file_date_us, file_date_ca = get_file_date_in_us_ca_formats(file)

        new_file = Path(
            self.audio_format.format(sort_dir=self.sorted_downloads, base_dir=base_name, parent_dir=parent_name,
                                    filename=filename, ext=ext, length=length, bitrate=bitrate,
                                    sample_rate=sample_rate, file_date_us=file_date_us, file_date_ca=file_date_ca))

        if await self.move_cd(file, new_file) is not False:
            await self.manager.progress_manager.sort_progress.increment_audio()

    async def sort_image(self, file: Path, base_name: str) -> None:
        """Sorts an image file into the sorted image folder"""
        self.image_count += 1

        try:
            image = Image.open(file)
            width, height = image.size
            resolution = f"{width}x{height}"
            image.close()
        except (PIL.UnidentifiedImageError, PIL.Image.DecompressionBombError):
            resolution = "Unknown"

        parent_name = file.parent.name
        filename, ext = file.stem, file.suffix
        file_date_us, file_date_ca = get_file_date_in_us_ca_formats(file)

        new_file = Path(
            self.image_format.format(sort_dir=self.sorted_downloads, base_dir=base_name, parent_dir=parent_name,
                                    filename=filename, ext=ext, resolution=resolution, file_date_us=file_date_us,
                                    file_date_ca=file_date_ca))

        if await self.move_cd(file, new_file) is not False:
            await self.manager.progress_manager.sort_progress.increment_image()

    async def sort_video(self, file: Path, base_name: str) -> None:
        """Sorts a video file into the sorted video folder"""
        self.video_count += 1

        try:
            props = get_video_properties(str(file))
            if 'width' in props and 'height' in props:
                width = str(props['width'])
                height = str(props['height'])
                resolution = f"{width}x{height}"
            else:
                resolution = "Unknown"
            frames_per_sec = str(props.get('avg_frame_rate', "Unknown"))
            codec = str(props.get('codec_name', "Unknown"))
        except (RuntimeError, subprocess.CalledProcessError):
            resolution = "Unknown"
            frames_per_sec = "Unknown"
            codec = "Unknown"

        parent_name = file.parent.name
        filename, ext = file.stem, file.suffix
        file_date_us, file_date_ca = get_file_date_in_us_ca_formats(file)

        new_file = Path(
            self.video_format.format(sort_dir=self.sorted_downloads, base_dir=base_name, parent_dir=parent_name,
                                    filename=filename, ext=ext, resolution=resolution, fps=frames_per_sec,
                                    codec=codec, file_date_us=file_date_us, file_date_ca=file_date_ca))

        if await self.move_cd(file, new_file) is not False:
            await self.manager.progress_manager.sort_progress.increment_video()

    async def sort_other(self, file: Path, base_name: str) -> None:
        """Sorts an other file into the sorted other folder"""
        self.other_count += 1

        parent_name = file.parent.name
        filename, ext = file.stem, file.suffix
        file_date_us, file_date_ca = get_file_date_in_us_ca_formats(file)

        new_file = Path(
            self.other_format.format(sort_dir=self.sorted_downloads, base_dir=base_name, parent_dir=parent_name,
                                    filename=filename, ext=ext, file_date_us=file_date_us, file_date_ca=file_date_ca))

        if await self.move_cd(file, new_file) is not False:
            await self.manager.progress_manager.sort_progress.increment_other()
