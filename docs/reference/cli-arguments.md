---
description: Here's the available CLI Arguments
---

# CLI Arguments

{% hint style="info" %}
Anything input as a CLI argument will take priority over config values.
{% endhint %}

For items not explained below, you can find their counterparts in the Configuration options to see what they do, or use `cyberdrop-dl --help` in your command prompt to get a full print out.

```
--config <name>                    : Name of the config file to load.
--proxy                            : Proxy connection string
--flaresolverr                     : IP:PORT for flaresolverr
--no-ui                            : Disables the UI and progress monitor
--download                         : Skips the UI and goes straight to downloading
--download-all-configs             : Runs all configs sequentially
--retry-failed                     : Retries failed links that are in the download history
--retry-all                        : Retries all downloads that are in the download history
--retry-maintenance                : Retries maintenance links that are in the download history, and were marked as completed

// Files
--input-file                       : Manually specify the URLs.txt file to load (path)
--output-folder                    : Manually specify the download directory (path)
--config-file                      : Manually specify the config file to load (path)
--appdata-folder                   : Manually specify where you want to program to store it's AppData folder
--log-folder                       : Manually specify where you want the program to save log files
--main-log-filename
--last-forum-post-filename
--unsupported-urls-filename
--download-error-urls-filename
--scrape-error-urls-filename

// Download Options
--block-download-sub-folders
--disable-download-attempt-limit
--disable-file-timestamps
--include-album-id-in-folder-name
--include-thread-id-in-folder-name
--remove-domains-from-folder-names
--remove-generated-id-from-filenames
--scrape-single-forum-post
--separate-posts
--skip-download-mark-completed

// File Size Limits
--maximum-image-size <number>
--minimum-image-size <number>
--maximum-video-size <number>
--minimum-video-size <number>
--maximum-other-size <number>
--minimum-other-size <number>

// Filtering Options
--completed-after                      : Filters downloads return by ;'--retry' options to those add/completed after the given date

--completed-before                     : Filters downloads return by '--retry' options to those add/completed before the given date

--max-items-retry                      : Limits the number of items returned by '--retry' options to the number given
// Ignore Options
--exclude-videos
--exclude-images
--excluse-audio
--exclude-other
--ignore-coomer-ads
--skip-hosts <domains>
--only-hosts <domains>

// Runtime Options
--ignore-history
--log-level
--skip-check-for-partial-files
--skip-check-for-empty-folders
--delete-partial-files
--send-unsupported-to-jdownloader

// Sorting Options
--sort-downloads
--sort-all-downloads                      : Only sort all downloads within a the scan_dir
--sort-folder
--scan-dir                                : set a directory to scan


// UI Options
--vi-mode
--refresh-rate
--scraping-item-limit
--downloading-item-limit
```
