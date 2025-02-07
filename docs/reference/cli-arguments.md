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
Anything input as a CLI argument will take priority over config values.
{% endhint %}

{% hint style="info" %}
Use `-` instead of `_` to separate words in an option name when using it as a CLI argument: Ex: `auto-dedupe` instead of `auto_dedupe`
{% endhint %}

You can pass any of the **Config Settings** and **Global Settings** options as a cli argument for the program

For items not explained below, you can find their counterparts in the configuration options to see what they do

## CLI only arguments

### `appdata-folder`

| Type           | Default  |
|----------------|----------|
| `Path` | `<Current Working Directory>`|

Folder where Cyberdrop-DL will store its data files.


### `completed-after`

| Type           | Default  |
|----------------|----------|
| `date` | `None` |

Only download files that were completed on or after this date. The date should be in ISO 8601 format, for example, `2021-12-23`

### `completed-before`

| Type           | Default  |
|----------------|----------|
| `date` | `None` |

Only download files that were completed on or before this date. The date should be in ISO 8601 format, for example, `2021-12-23`

### `config`

| Type           | Default  |
|----------------|----------|
| `str` | `None` |

Name of config to load. Use `ALL` to run all configs sequentially

### `config-file`

| Type           | Default  |
|----------------|----------|
| `Path` | `None` |

Path to the CDL `settings.yaml` file to load

{% hint style="info" %}
If both `config` and `config-file` are supplied, `config-file` takes priority
{% endhint %}

### `download`  

| Type           | Default  | Action |
|----------------|----------|--------|
| `BoolFlag` | `False` | `store_true`|

Skips UI, start download immediately

### `download-tiktok-audios`

| Type           | Default  | Action |
|----------------|----------|--------|
| `BoolFlag` | `False` | `store_true`|

Download TikTok audios from posts and save them as separate files

### `max-items-retry`

| Type           | Default  |
|----------------|----------|
| `NonNegativeInt` | `0` |

Max number of links to retry. Using `0` means no limit

### `no-ui`  

| Type           | Default  | Action |
|----------------|----------|--------|
| `BoolFlag` | `False` | `store_true`|

Disables the UI/progress view entirely

### `retry-all`

| Type           | Default  | Action |
|----------------|----------|--------|
| `BoolFlag` | `False` | `store_true`|

Retry all downloads

### `retry-failed`  

| Type           | Default  | Action |
|----------------|----------|--------|
| `BoolFlag` | `False` | `store_true`|

Retry failed downloads

### `retry-maintenance`  

| Type           | Default  | Action |
|----------------|----------|--------|
| `BoolFlag` | `False` | `store_true`|

Retry download of maintenance files (bunkr). Requires files to be hashed

***

## Overview

Bool arguments like options within `Download Options`, `Ignore Options`, `Runtime Options`, etc. can be prefixed with `--no-` to negate them. Ex: `--no-auto-dedupe` will disable auto dedupe, overriding whatever the config option was set to.

```shell
usage: cyberdrop-dl [OPTIONS] URL [URL...]

Bulk asynchronous downloader for multiple file hosts

options:
  -h, --help            show this help message and exit
  -V, --version         show program's version number and exit

CLI-only Options:
  LINK(S)               link(s) to content to download (passing multiple links is supported)
  --appdata-folder APPDATA_FOLDER
                        AppData folder path (default: None)
  --completed-after COMPLETED_AFTER
                        only download completed downloads at or after this date (default: None)
  --completed-before COMPLETED_BEFORE
                        only download completed downloads at or before this date (default: None)
  --config CONFIG       name of config to load (default: None)
  --config-file CONFIG_FILE
                        path to the CDL settings.yaml file to load (default: None)
  --download            skips UI, start download immediatly (default: False)
  --max-items-retry MAX_ITEMS_RETRY
                        max number of links to retry (default: 0)
  --no-ui               disables the UI/progress view entirely (default: False)
  --retry-all           retry all downloads (default: False)
  --retry-failed        retry failed downloads (default: False)
  --retry-maintenance   retry download of maintenance files (bunkr). Requires files to be hashed (default: False)
  --download-tiktok-audios
                        download TikTok audios (default: False)

browser_cookies:
  --browsers [BROWSERS ...]
  --auto-import, --no-auto-import
  --sites [SITES ...]

download_options:
  --block-download-sub-folders, --no-block-download-sub-folders
  --disable-download-attempt-limit, --no-disable-download-attempt-limit
  --disable-file-timestamps, --no-disable-file-timestamps
  --include-album-id-in-folder-name, --no-include-album-id-in-folder-name
  --include-thread-id-in-folder-name, --no-include-thread-id-in-folder-name
  --remove-domains-from-folder-names, --no-remove-domains-from-folder-names
  --remove-generated-id-from-filenames, --no-remove-generated-id-from-filenames
  --scrape-single-forum-post, --no-scrape-single-forum-post
  --separate-posts, --no-separate-posts
  --separate-posts-format SEPARATE_POSTS_FORMAT
  --skip-download-mark-completed, --no-skip-download-mark-completed
  --skip-referer-seen-before, --no-skip-referer-seen-before
  --maximum-number-of-children [MAXIMUM_NUMBER_OF_CHILDREN ...]
  --maximum-thread-depth MAX_THREAD_NESTING

dupe_cleanup_options:
  --hashing HASHING
  --auto-dedupe, --no-auto-dedupe
  --add-md5-hash, --no-add-md5-hash
  --add-sha256-hash, --no-add-sha256-hash
  --send-deleted-to-trash, --no-send-deleted-to-trash

file_size_limits:
  --maximum-image-size MAXIMUM_IMAGE_SIZE
  --maximum-other-size MAXIMUM_OTHER_SIZE
  --maximum-video-size MAXIMUM_VIDEO_SIZE
  --minimum-image-size MINIMUM_IMAGE_SIZE
  --minimum-other-size MINIMUM_OTHER_SIZE
  --minimum-video-size MINIMUM_VIDEO_SIZE

files:
  -i INPUT_FILE, --input-file INPUT_FILE
  -d DOWNLOAD_FOLDER, --download-folder DOWNLOAD_FOLDER

ignore_options:
  --exclude-videos, --no-exclude-videos
  --exclude-images, --no-exclude-images
  --exclude-audio, --no-exclude-audio
  --exclude-other, --no-exclude-other
  --ignore-coomer-ads, --no-ignore-coomer-ads
  --skip-hosts [SKIP_HOSTS ...]
  --only-hosts [ONLY_HOSTS ...]
  --filename-regex-filter FILENAME_REGEX_FILTER

logs:
  --log-folder LOG_FOLDER
  --webhook WEBHOOK
  --main-log MAIN_LOG
  --last-forum-post LAST_FORUM_POST
  --unsupported-urls UNSUPPORTED_URLS
  --download-error-urls DOWNLOAD_ERROR_URLS
  --scrape-error-urls SCRAPE_ERROR_URLS
  --rotate-logs, --no-rotate-logs
  --log-line-width LOG_LINE_WIDTH
  --logs-expire-after LOGS_EXPIRE_AFTER

runtime_options:
  --ignore-history, --no-ignore-history
  --log-level LOG_LEVEL
  --console-log-level CONSOLE_LOG_LEVEL
  --skip-check-for-partial-files, --no-skip-check-for-partial-files
  --skip-check-for-empty-folders, --no-skip-check-for-empty-folders
  --delete-partial-files, --no-delete-partial-files
  --update-last-forum-post, --no-update-last-forum-post
  --send-unsupported-to-jdownloader, --no-send-unsupported-to-jdownloader
  --jdownloader-download-dir JDOWNLOADER_DOWNLOAD_DIR
  --jdownloader-autostart, --no-jdownloader-autostart
  --jdownloader-whitelist [JDOWNLOADER_WHITELIST ...]
  --deep-scrape, --no-deep-scrape
  --slow-download-speed SLOW_DOWNLOAD_SPEED

sorting:
  --sort-downloads, --no-sort-downloads
  --sort-folder SORT_FOLDER
  --scan-folder SCAN_FOLDER
  --sort-incrementer-format SORT_INCREMENTER_FORMAT
  --sorted-audio SORTED_AUDIO
  --sorted-image SORTED_IMAGE
  --sorted-other SORTED_OTHER
  --sorted-video SORTED_VIDEO

general:
  --allow-insecure-connections, --no-allow-insecure-connections
  --user-agent USER_AGENT
  --proxy PROXY
  --flaresolverr FLARESOLVERR
  --max-file-name-length MAX_FILE_NAME_LENGTH
  --max-folder-name-length MAX_FOLDER_NAME_LENGTH
  --required-free-space REQUIRED_FREE_SPACE

rate_limiting_options:
  --connection-timeout CONNECTION_TIMEOUT
  --download-attempts DOWNLOAD_ATTEMPTS
  --read-timeout READ_TIMEOUT
  --rate-limit RATE_LIMIT
  --download-delay DOWNLOAD_DELAY
  --max-simultaneous-downloads MAX_SIMULTANEOUS_DOWNLOADS
  --max-simultaneous-downloads-per-domain MAX_SIMULTANEOUS_DOWNLOADS_PER_DOMAIN
  --download-speed-limit DOWNLOAD_SPEED_LIMIT
  --file-host-cache-expire-after FILE_HOST_CACHE_EXPIRE_AFTER
  --forum-cache-expire-after FORUM_CACHE_EXPIRE_AFTER

ui_options:
  --vi-mode, --no-vi-mode
  --refresh-rate REFRESH_RATE
  --scraping-item-limit SCRAPING_ITEM_LIMIT
  --downloading-item-limit DOWNLOADING_ITEM_LIMIT

Deprecated:
  --output-folder OUTPUT_FOLDER
  --download-all-configs
                        Skip the UI and go straight to downloading (runs all configs sequentially)
  --sort-all-configs    Sort all configs sequentially
  --sort-all-downloads  sort all downloads, not just those downloaded by Cyberdrop-DL
  --sort-cdl-only       only sort files downloaded by Cyberdrop-DL
  --main-log-filename MAIN_LOG_FILENAME
  --last-forum-post-filename LAST_FORUM_POST_FILENAME
  --unsupported-urls-filename UNSUPPORTED_URLS_FILENAME
  --download-error-urls-filename DOWNLOAD_ERROR_URLS_FILENAME
  --scrape-error-urls-filename SCRAPE_ERROR_URLS_FILENAME
```
