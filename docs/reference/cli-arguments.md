---
icon: rectangle-terminal
description: Here's the available CLI Arguments
layout:
  title:
    visible: true
  description:
    visible: true
  tableOfContents:
    visible: true
  outline:
    visible: false
  pagination:
    visible: true
---

# CLI Arguments

{% hint style="info" %}
CLI inputs always take priority over config values.
{% endhint %}

{% hint style="info" %}
Use `-` instead of `_` to separate words in an config option name when using it as a CLI argument: Ex: `auto_dedupe` needs to be `auto-dedupe` when using it via the CLI
{% endhint %}

You can pass any of the **Config Settings** and **Global Settings** options as a cli argument for the program.

For items not explained below, you can find their counterparts in the configuration options to see what they do.

## CLI only arguments

### `appdata-folder`

| Type   | Default                       |
| ------ | ----------------------------- |
| `Path` | `<Current Working Directory>` |

Folder where Cyberdrop-DL will store it's database, cache and config files.

### `completed-after`

| Type   | Default |
| ------ | ------- |
| `date` | `None`  |

Only download files that were completed on or after this date. The date should be in ISO 8601 format, for example, `2021-12-23`

### `completed-before`

| Type   | Default |
| ------ | ------- |
| `date` | `None`  |

Only download files that were completed on or before this date. The date should be in ISO 8601 format, for example, `2021-12-23`

### `config`

| Type  | Default |
| ----- | ------- |
| `str` | `None`  |

Name of config to load. Use `ALL` to run all configs sequentially

### `config-file`

| Type   | Default |
| ------ | ------- |
| `Path` | `None`  |

Path to the CDL `settings.yaml` file to load

{% hint style="info" %}
If both `config` and `config-file` are supplied, `config-file` takes priority
{% endhint %}

### `disable-cache`  

| Type       | Default | Action       |
| ---------- | ------- | ------------ |
| `BoolFlag` | `False` | `store_true` |

Disables the use of the requests cache for the current run only. All config settings or arguments related to the cache (ex: `file_host_cache_expire_after`) will be ignored.

{% hint style="info" %}
This does not affect the original cache
{% endhint %}

### `download`  

| Type       | Default | Action       |
| ---------- | ------- | ------------ |
| `BoolFlag` | `False` | `store_true` |

Skips UI, start download immediately

### `download-dropbox-folders-as-zip`


| Type       | Default | Action       |
| ---------- | ------- | ------------ |
| `BoolFlag` | `False` | `store_true` |

Folder downloads from Dropbox are disabled by default because they will be downloaded as a single zip file. Enable them with this option

### `download-tiktok-audios`

| Type       | Default | Action       |
| ---------- | ------- | ------------ |
| `BoolFlag` | `False` | `store_true` |

Download TikTok audios from posts and save them as separate files

### `max-items-retry`

| Type             | Default |
| ---------------- | ------- |
| `NonNegativeInt` | `0`     |

Max number of links to retry. Using `0` means no limit

### `portrait`

| Type       | Default | Action       |
| ---------- | ------- | ------------ |
| `BoolFlag` | `False` | `store_true` |

Run CDL with a vertical layout

### `retry-all`

| Type       | Default | Action       |
| ---------- | ------- | ------------ |
| `BoolFlag` | `False` | `store_true` |

Retry all downloads

### `retry-failed`  

| Type       | Default | Action       |
| ---------- | ------- | ------------ |
| `BoolFlag` | `False` | `store_true` |

Retry failed downloads

### `retry-maintenance`  

| Type       | Default | Action       |
| ---------- | ------- | ------------ |
| `BoolFlag` | `False` | `store_true` |

Retry download of maintenance files (bunkr). Requires files to be hashed

### `show-supported-sites`  

| Type       | Default | Action       |
| ---------- | ------- | ------------ |
| `BoolFlag` | `False` | `store_true` |

Shows a list of all supported sites and exits

### `ui`  

| Type       | Default |
| ---------- | ------- |
| `CaseInsensitiveStrEnum` | `FULLSCREEN` |

UI can have 1 of these values:

- `DISABLED` : no output at all
- `ACTIVITY` : only shows a spinner with the text `running CDL`
- `SIMPLE`: shows spinner + simplified progress bar
- `FULLSCREEN`: shows the normal UI/progress view

Values are case insensitive, ex: both `disabled` and `DISABLED` are valid

## Overview

Bool arguments like options within `Download Options`, `Ignore Options`, `Runtime Options`, etc. can be prefixed with `--no-` to negate them. Ex: `--no-auto-dedupe` will disable auto dedupe, overriding whatever the config option was set to.

```shell
usage: cyberdrop-dl [OPTIONS] URL [URL...]

Bulk asynchronous downloader for multiple file hosts

options:
  -h, --help                                                                    show this help message and exit
  -V, --version                                                                 show CDL version number and exit

CLI-only options:
  LINK(S)                                                                       link(s) to content to download (passing multiple links is supported)
  --appdata-folder APPDATA_FOLDER                                               AppData folder path
  --completed-after COMPLETED_AFTER                                             only download completed downloads at or after this date
  --completed-before COMPLETED_BEFORE                                           only download completed downloads at or before this date
  --config CONFIG                                                               name of config to load
  --config-file CONFIG_FILE                                                     path to the CDL settings.yaml file to load
  --disable-cache                                                               Temporarily disable the requests cache
  --download                                                                    skips UI, start download immediatly
  --download-dropbox-folders-as-zip                                             download Dropbox folder without api key as zip
  --download-tiktok-audios                                                      download TikTok audios
  --max-items-retry MAX_ITEMS_RETRY                                             max number of links to retry
  --portrait                                                                    show UI in a portrait layout
  --print-stats                                                                 Show stats report at the end of a run
  --retry-all                                                                   retry all downloads
  --retry-failed                                                                retry failed downloads
  --retry-maintenance                                                           retry download of maintenance files (bunkr). Requires files to be hashed
  --show-supported-sites                                                        shows a list of supported sites and exits
  --ui UI                                                                       DISABLED, ACTIVITY, SIMPLE or FULLSCREEN

browser_cookies:
  --auto-import, --no-auto-import
  --browser BROWSER
  --sites [SITES ...]

download_options:
  --block-download-sub-folders, --no-block-download-sub-folders
  --disable-download-attempt-limit, --no-disable-download-attempt-limit
  --disable-file-timestamps, --no-disable-file-timestamps
  --include-album-id-in-folder-name, --no-include-album-id-in-folder-name
  --include-thread-id-in-folder-name, --no-include-thread-id-in-folder-name
  --maximum-number-of-children [MAXIMUM_NUMBER_OF_CHILDREN ...]
  --remove-domains-from-folder-names, --no-remove-domains-from-folder-names
  --remove-generated-id-from-filenames, --no-remove-generated-id-from-filenames
  --scrape-single-forum-post, --no-scrape-single-forum-post
  --separate-posts-format SEPARATE_POSTS_FORMAT
  --separate-posts, --no-separate-posts
  --skip-download-mark-completed, --no-skip-download-mark-completed
  --skip-referer-seen-before, --no-skip-referer-seen-before
  --maximum-thread-depth MAXIMUM_THREAD_DEPTH

dupe_cleanup_options:
  --add-md5-hash, --no-add-md5-hash
  --add-sha256-hash, --no-add-sha256-hash
  --auto-dedupe, --no-auto-dedupe
  --hashing HASHING
  --send-deleted-to-trash, --no-send-deleted-to-trash

file_size_limits:
  --maximum-image-size MAXIMUM_IMAGE_SIZE
  --maximum-other-size MAXIMUM_OTHER_SIZE
  --maximum-video-size MAXIMUM_VIDEO_SIZE
  --minimum-image-size MINIMUM_IMAGE_SIZE
  --minimum-other-size MINIMUM_OTHER_SIZE
  --minimum-video-size MINIMUM_VIDEO_SIZE

media_duration_limits:
  --maximum-video-duration MAXIMUM_VIDEO_DURATION
  --maximum-audio-duration MAXIMUM_AUDIO_DURATION
  --minimum-video-duration MINIMUM_VIDEO_DURATION
  --minimum-audio-duration MINIMUM_AUDIO_DURATION

files:
  -d DOWNLOAD_FOLDER, --download-folder DOWNLOAD_FOLDER
  -j, --dump-json, --no-dump-json
  -i INPUT_FILE, --input-file INPUT_FILE
  --save-pages-html, --no-save-pages-html

ignore_options:
  --exclude-audio, --no-exclude-audio
  --exclude-images, --no-exclude-images
  --exclude-other, --no-exclude-other
  --exclude-videos, --no-exclude-videos
  --filename-regex-filter FILENAME_REGEX_FILTER
  --ignore-coomer-ads, --no-ignore-coomer-ads
  --only-hosts [ONLY_HOSTS ...]
  --skip-hosts [SKIP_HOSTS ...]
  --exclude-files-with-no-extension, --no-exclude-files-with-no-extension

logs:
  --download-error-urls DOWNLOAD_ERROR_URLS
  --last-forum-post LAST_FORUM_POST
  --log-folder LOG_FOLDER
  --log-line-width LOG_LINE_WIDTH
  --logs-expire-after LOGS_EXPIRE_AFTER
  --main-log MAIN_LOG
  --rotate-logs, --no-rotate-logs
  --scrape-error-urls SCRAPE_ERROR_URLS
  --unsupported-urls UNSUPPORTED_URLS
  --webhook WEBHOOK

runtime_options:
  --console-log-level CONSOLE_LOG_LEVEL
  --deep-scrape, --no-deep-scrape
  --delete-partial-files, --no-delete-partial-files
  --ignore-history, --no-ignore-history
  --jdownloader-autostart, --no-jdownloader-autostart
  --jdownloader-download-dir JDOWNLOADER_DOWNLOAD_DIR
  --jdownloader-whitelist [JDOWNLOADER_WHITELIST ...]
  --log-level LOG_LEVEL
  --send-unsupported-to-jdownloader, --no-send-unsupported-to-jdownloader
  --skip-check-for-empty-folders, --no-skip-check-for-empty-folders
  --skip-check-for-partial-files, --no-skip-check-for-partial-files
  --slow-download-speed SLOW_DOWNLOAD_SPEED
  --update-last-forum-post, --no-update-last-forum-post

sorting:
  --scan-folder SCAN_FOLDER
  --sort-downloads, --no-sort-downloads
  --sort-folder SORT_FOLDER
  --sort-incrementer-format SORT_INCREMENTER_FORMAT
  --sorted-audio SORTED_AUDIO
  --sorted-image SORTED_IMAGE
  --sorted-other SORTED_OTHER
  --sorted-video SORTED_VIDEO

general:
  --ssl-context SSL_CONTEXT
  --disable-crawlers [DISABLE_CRAWLERS ...]
  --enable-generic-crawler, --no-enable-generic-crawler
  --flaresolverr FLARESOLVERR
  --max-file-name-length MAX_FILE_NAME_LENGTH
  --max-folder-name-length MAX_FOLDER_NAME_LENGTH
  --proxy PROXY
  --required-free-space REQUIRED_FREE_SPACE
  --user-agent USER_AGENT

rate_limiting_options:
  --connection-timeout CONNECTION_TIMEOUT
  --download-attempts DOWNLOAD_ATTEMPTS
  --download-delay DOWNLOAD_DELAY
  --download-speed-limit DOWNLOAD_SPEED_LIMIT
  --file-host-cache-expire-after FILE_HOST_CACHE_EXPIRE_AFTER
  --forum-cache-expire-after FORUM_CACHE_EXPIRE_AFTER
  --jitter JITTER
  --max-simultaneous-downloads-per-domain MAX_SIMULTANEOUS_DOWNLOADS_PER_DOMAIN
  --max-simultaneous-downloads MAX_SIMULTANEOUS_DOWNLOADS
  --rate-limit RATE_LIMIT
  --read-timeout READ_TIMEOUT

ui_options:
  --downloading-item-limit DOWNLOADING_ITEM_LIMIT
  --refresh-rate REFRESH_RATE
  --scraping-item-limit SCRAPING_ITEM_LIMIT
  --vi-mode, --no-vi-mode

generic_crawlers_instances:
  --wordpress-media [WORDPRESS_MEDIA ...]
  --wordpress-html [WORDPRESS_HTML ...]
  --discourse [DISCOURSE ...]
  --chevereto [CHEVERETO ...]

```
