from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from cyberdrop_dl.config_definitions import AuthSettings, ConfigSettings, GlobalSettings
from cyberdrop_dl.utils import yaml

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


def transfer_v4_config(manager: Manager, new_config_name: str, old_config_path: Path) -> None:
    """Transfers a V4 config into V5 possession."""
    new_auth_data = AuthSettings()
    new_user_data = ConfigSettings()
    new_global_data = GlobalSettings()
    old_data = yaml.load(old_config_path)
    old_data = old_data["Configuration"]

    from cyberdrop_dl.managers.path_manager import constants

    new_user_data.files.input_file = constants.APP_STORAGE / "Configs" / new_config_name / "URLs.txt"
    new_user_data.files.download_folder = constants.DOWNLOAD_STORAGE / "Cyberdrop-DL Downloads"
    new_user_data.logs.log_folder = constants.APP_STORAGE / "Configs" / new_config_name / "Logs"
    new_user_data.sorting.sort_folder = constants.DOWNLOAD_STORAGE / "Cyberdrop-DL Sorted Downloads"

    # Auth data transfer
    new_auth_data.forums.nudostar_username = old_data["Authentication"]["nudostar_username"]
    new_auth_data.forums.nudostar_password = old_data["Authentication"]["nudostar_password"]
    new_auth_data.forums.simpcity_username = old_data["Authentication"]["simpcity_username"]
    new_auth_data.forums.simpcity_password = old_data["Authentication"]["simpcity_password"]
    new_auth_data.forums.socialmediagirls_username = old_data["Authentication"]["socialmediagirls_username"]
    new_auth_data.forums.socialmediagirls_password = old_data["Authentication"]["socialmediagirls_password"]
    new_auth_data.forums.xbunker_username = old_data["Authentication"]["xbunker_username"]
    new_auth_data.forums.xbunker_password = old_data["Authentication"]["xbunker_password"]

    new_auth_data.jdownloader.username = old_data["JDownloader"]["jdownloader_username"]
    new_auth_data.jdownloader.password = old_data["JDownloader"]["jdownloader_password"]
    new_auth_data.jdownloader.device = old_data["JDownloader"]["jdownloader_device"]

    new_auth_data.reddit.personal_use_script = old_data["Authentication"]["reddit_personal_use_script"]
    new_auth_data.reddit.secret = old_data["Authentication"]["reddit_secret"]

    new_auth_data.gofile.api_key = old_data["Authentication"]["gofile_api_key"]
    new_auth_data.imgur.client_id = old_data["Authentication"]["imgur_client_id"]
    new_auth_data.pixeldrain.api_key = old_data["Authentication"]["pixeldrain_api_key"]

    # User data transfer
    new_user_data.download_options.block_download_sub_folders = old_data["Runtime"]["block_sub_folders"]
    new_user_data.download_options.disable_download_attempt_limit = old_data["Runtime"]["disable_attempt_limit"]
    new_user_data.download_options.include_album_id_in_folder_name = old_data["Runtime"]["include_id"]
    new_user_data.download_options.remove_generated_id_from_filenames = old_data["Runtime"]["remove_bunkr_identifier"]
    new_user_data.download_options.separate_posts = old_data["Forum_Options"]["separate_posts"]
    new_user_data.download_options.skip_download_mark_completed = False

    new_user_data.file_size_limits.maximum_image_size = old_data["Runtime"]["filesize_maximum_images"]
    new_user_data.file_size_limits.maximum_other_size = old_data["Runtime"]["filesize_maximum_other"]
    new_user_data.file_size_limits.maximum_video_size = old_data["Runtime"]["filesize_maximum_videos"]
    new_user_data.file_size_limits.minimum_image_size = old_data["Runtime"]["filesize_minimum_images"]
    new_user_data.file_size_limits.minimum_other_size = old_data["Runtime"]["filesize_minimum_other"]
    new_user_data.file_size_limits.minimum_video_size = old_data["Runtime"]["filesize_minimum_videos"]

    new_user_data.ignore_options.exclude_videos = old_data["Ignore"]["exclude_videos"]
    new_user_data.ignore_options.exclude_images = old_data["Ignore"]["exclude_images"]
    new_user_data.ignore_options.exclude_other = old_data["Ignore"]["exclude_other"]
    new_user_data.ignore_options.exclude_audio = old_data["Ignore"]["exclude_audio"]
    new_user_data.ignore_options.ignore_coomer_ads = old_data["Ignore"]["skip_coomer_ads"]
    new_user_data.ignore_options.skip_hosts = old_data["Ignore"]["skip_hosts"]
    new_user_data.ignore_options.only_hosts = old_data["Ignore"]["only_hosts"]

    new_user_data.runtime_options.ignore_history = old_data["Ignore"]["ignore_history"]
    new_user_data.runtime_options.skip_check_for_partial_files = old_data["Runtime"][
        "skip_check_for_partial_files_and_empty_dirs"
    ]
    new_user_data.runtime_options.skip_check_for_empty_folders = old_data["Runtime"][
        "skip_check_for_partial_files_and_empty_dirs"
    ]
    new_user_data.runtime_options.send_unsupported_to_jdownloader = old_data["JDownloader"]["apply_jdownloader"]

    new_user_data.sorting.sort_downloads = old_data["Sorting"]["sort_downloads"]

    # Global data transfer
    new_global_data.general.allow_insecure_connections = old_data["Runtime"]["allow_insecure_connections"]
    new_global_data.general.user_agent = old_data["Runtime"]["user_agent"]
    new_global_data.general.proxy = old_data["Runtime"]["proxy"] or None
    new_global_data.general.max_file_name_length = old_data["Runtime"]["max_filename_length"]
    new_global_data.general.max_folder_name_length = old_data["Runtime"]["max_folder_name_length"]
    new_global_data.general.required_free_space = old_data["Runtime"]["required_free_space"]

    new_global_data.rate_limiting_options.connection_timeout = old_data["Ratelimiting"]["connection_timeout"]
    new_global_data.rate_limiting_options.download_attempts = old_data["Runtime"]["attempts"]
    new_global_data.rate_limiting_options.download_delay = old_data["Ratelimiting"]["throttle"]
    new_global_data.rate_limiting_options.read_timeout = old_data["Ratelimiting"]["read_timeout"]
    new_global_data.rate_limiting_options.rate_limit = old_data["Ratelimiting"]["ratelimit"]
    new_global_data.rate_limiting_options.max_simultaneous_downloads_per_domain = old_data["Runtime"][
        "max_concurrent_downloads_per_domain"
    ]

    # Save Data
    new_settings = manager.path_manager.config_folder / new_config_name / "settings.yaml"
    new_logs = manager.path_manager.config_folder / new_config_name / "Logs"
    new_settings.parent.mkdir(parents=True, exist_ok=True)
    new_logs.mkdir(parents=True, exist_ok=True)

    old_config_folder = Path(old_config_path).parent
    old_input_file: str = old_data["Files"]["input_file"]
    old_urls_path = Path(old_input_file.replace("{config}", old_config_folder.name))

    new_urls = manager.path_manager.config_folder / new_config_name / "URLs.txt"
    new_urls.touch(exist_ok=True)

    if not old_urls_path.is_absolute() and len(old_urls_path.parts) == 1:
        old_urls_path = old_config_folder / old_urls_path.name

    if old_urls_path.is_file():
        with old_urls_path.open(encoding="utf8") as urls_file:
            urls = urls_file.readlines()
        with new_urls.open("w", encoding="utf8") as urls_file:
            urls_file.writelines(urls)
    else:
        new_urls.touch(exist_ok=True)

    manager.config_manager.authentication_data = AuthSettings.model_validate(new_auth_data.model_dump())
    manager.config_manager.global_settings_data = GlobalSettings.model_validate(new_global_data.model_dump())
    manager.config_manager.save_as_new_config(new_settings, ConfigSettings.model_validate(new_user_data.model_dump()))
    manager.config_manager.write_updated_authentication_config()
    manager.config_manager.write_updated_global_settings_config()
    manager.config_manager.change_config(new_config_name)
