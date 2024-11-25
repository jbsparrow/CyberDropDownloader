from __future__ import annotations

from cyberdrop_dl.utils import constants

authentication_settings: dict = {
    "Forums": {
        "celebforum_xf_user_cookie": "",
        "celebforum_username": "",
        "celebforum_password": "",
        "f95zone_xf_user_cookie": "",
        "f95zone_username": "",
        "f95zone_password": "",
        "leakedmodels_xf_user_cookie": "",
        "leakedmodels_username": "",
        "leakedmodels_password": "",
        "nudostar_xf_user_cookie": "",
        "nudostar_username": "",
        "nudostar_password": "",
        "simpcity_xf_user_cookie": "",
        "simpcity_username": "",
        "simpcity_password": "",
        "socialmediagirls_xf_user_cookie": "",
        "socialmediagirls_username": "",
        "socialmediagirls_password": "",
        "xbunker_xf_user_cookie": "",
        "xbunker_username": "",
        "xbunker_password": "",
    },
    "Coomer": {
        "session": "",
    },
    "XXXBunker": {
        "PHPSESSID": "",
    },
    "GoFile": {
        "gofile_api_key": "",
    },
    "Imgur": {
        "imgur_client_id": "",
    },
    "JDownloader": {
        "jdownloader_username": "",
        "jdownloader_password": "",
        "jdownloader_device": "",
    },
    "PixelDrain": {
        "pixeldrain_api_key": "",
    },
    "RealDebrid": {
        "realdebrid_api_key": "",
    },
    "Reddit": {
        "reddit_personal_use_script": "",
        "reddit_secret": "",
    },
}

settings: dict = {
    "Download_Options": {
        "block_download_sub_folders": False,
        "disable_download_attempt_limit": False,
        "disable_file_timestamps": False,
        "include_album_id_in_folder_name": False,
        "include_thread_id_in_folder_name": False,
        "remove_domains_from_folder_names": False,
        "remove_generated_id_from_filenames": False,
        "scrape_single_forum_post": False,
        "separate_posts": False,
        "skip_download_mark_completed": False,
        "skip_referer_seen_before": False,
        "maximum_number_of_children": [],
    },
    "Files": {
        "input_file": str(constants.APP_STORAGE / "Configs" / "{config}" / "URLs.txt"),
        "download_folder": str(constants.DOWNLOAD_STORAGE),
    },
    "Logs": {
        "log_folder": str(constants.APP_STORAGE / "Configs" / "{config}" / "Logs"),
        "webhook_url": "",
        "main_log_filename": "downloader.log",
        "last_forum_post_filename": "Last_Scraped_Forum_Posts.csv",
        "unsupported_urls_filename": "Unsupported_URLs.csv",
        "download_error_urls_filename": "Download_Error_URLs.csv",
        "scrape_error_urls_filename": "Scrape_Error_URLs.csv",
        "rotate_logs": False,
    },
    "File_Size_Limits": {
        "maximum_image_size": 0,
        "maximum_other_size": 0,
        "maximum_video_size": 0,
        "minimum_image_size": 0,
        "minimum_other_size": 0,
        "minimum_video_size": 0,
    },
    "Ignore_Options": {
        "exclude_videos": False,
        "exclude_images": False,
        "exclude_audio": False,
        "exclude_other": False,
        "ignore_coomer_ads": False,
        "skip_hosts": [],
        "only_hosts": [],
    },
    "Runtime_Options": {
        "ignore_history": False,
        "log_level": 10,
        "console_log_level": 100,
        "skip_check_for_partial_files": False,
        "skip_check_for_empty_folders": False,
        "delete_partial_files": False,
        "update_last_forum_post": True,
        "send_unsupported_to_jdownloader": False,
        "jdownloader_download_dir": None,
        "jdownloader_autostart": False,
        "jdownloader_whitelist": [],
    },
    "Sorting": {
        "sort_downloads": False,
        "sort_folder": str(constants.DOWNLOAD_STORAGE / "Cyberdrop-DL Sorted Downloads"),
        "scan_folder": None,
        "sort_cdl_only": True,
        "sort_incremementer_format": " ({i})",
        "sorted_audio": "{sort_dir}/{base_dir}/Audio/{filename}{ext}",
        "sorted_image": "{sort_dir}/{base_dir}/Images/{filename}{ext}",
        "sorted_other": "{sort_dir}/{base_dir}/Other/{filename}{ext}",
        "sorted_video": "{sort_dir}/{base_dir}/Videos/{filename}{ext}",
    },
    "Browser_Cookies": {
        "browsers": ["Chrome"],
        "auto_import": False,
        "sites": [],
    },
    "Dupe_Cleanup_Options": {
        "hashing": "IN_PLACE",
        "auto_dedupe": True,
        "add_md5_hash": False,
        "add_sha256_hash": False,
        "send_deleted_to_trash": True,
    },
}

global_settings: dict = {
    "General": {
        "allow_insecure_connections": False,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
        "proxy": "",
        "flaresolverr": "",
        "max_file_name_length": 95,
        "max_folder_name_length": 60,
        "required_free_space": 5,
    },
    "Rate_Limiting_Options": {
        "connection_timeout": 15,
        "download_attempts": 5,
        "read_timeout": 300,
        "rate_limit": 50,
        "download_delay": 0.5,
        "max_simultaneous_downloads": 15,
        "max_simultaneous_downloads_per_domain": 3,
        "download_speed_limit": 0,
    },
    "UI_Options": {
        "vi_mode": False,
        "refresh_rate": 10,
        "scraping_item_limit": 5,
        "downloading_item_limit": 5,
    },
}
