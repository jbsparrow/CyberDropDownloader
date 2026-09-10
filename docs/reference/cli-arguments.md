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
Use `-` instead of `_` to separate words in an config option name when using it as a CLI argument:

Ex: `delete_partial_files` needs to be `delete-partial-files` when using it via the CLI
{% endhint %}

All config option except authentication credentials have a CLI equivalent to override them.

For items not explained below, you can find their counterparts in the configuration options to see what they do.

## CLI only arguments

These options can only be supplied via CLI argmunets. They are not included on the config file

### `--config-file`

| Type   | Default |
| ------ | ------- |
| `Path` | `null`  |

Path to the config file to use for this session. The config file at the default location will be ignored. This file _must_ have a `.yml` or `.yaml` extension

{% hint style="info" %}
If provided, this file _must_ exists already, but it can be empty
{% endhint %}

### `--cache-file`

| Type   | Default |
| ------ | ------- |
| `Path` | `null`  |

Path to the cache file to use for this session. The cache at the default location will be ignored. This file _must_ have a `.json` extension

{% hint style="info" %}
If provided, this file _must_ exists already, but it can be empty
{% endhint %}

### `--database-file`

| Type   | Default |
| ------ | ------- |
| `Path` | `null`  |

Path to the database file to use for this session. The database at the default location will be ignored. This file _must_ have a `.db` extension

{% hint style="info" %}
If provided, this file _must_ exists already, but it can be empty
{% endhint %}

## Overview

<!-- START_CLI_OVERVIEW -->
```shell
cyberdrop-dl v10.8.0
Bulk asynchronous downloader for multiple file hosts

Usage: cyberdrop-dl COMMAND [OPTIONS]

Run 'cyberdrop-dl' without arguments to start the interactive TUI

╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────╮
│ cache      Cache operations                                                                      │
│ cleanup    Perform maintenance tasks                                                             │
│ config     Config file operations                                                                │
│ database   Commands for managing the database                                                    │
│ download   Download URLs                                                                         │
│ hash       Compute and save hashes of every file in a folder (recursively)                       │
│ report     Generate and display information about the system                                     │
│ retry      Retry downloads from the database                                                     │
│ show       Show a list of all supported sites                                                    │
│ --help -h  Display this message and exit.                                                        │
│ --version  Display application version.                                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Parameters ─────────────────────────────────────────────────────────────────────────────────────╮
│ --input-file --input -i    Text/HTML file with URL(s) to download                                │
│ --config-file --config -c  YAML file to use as config                                            │
│ --cache-file               JSON file to use as cache                                             │
│ --database-file --db       SQLite file to use as database                                        │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯

Github:      https://github.com/Cyberdrop-DL/cyberdrop-dl
Wiki (docs): https://script-ware.gitbook.io/cyberdrop-dl

────────────────────────────────────────────────────────────────────────────────────────────────────

cyberdrop-dl v10.8.0
Bulk asynchronous downloader for multiple file hosts

Usage: cyberdrop-dl download [OPTIONS] [ARGS...]

Download URLs

╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────╮
│ URLS_OR_FILES  File(s)/ URL(s) to download                                                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Parameters ─────────────────────────────────────────────────────────────────────────────────────╮
│ --input-file                        Text/HTML file with URL(s) to download                       │
│ --input-folder                      Read all '.txt' within this folder for URL(s) to download    │
│                                     (non recursive).                                             │
│                                                 All URLs within the same file will be grouped in │
│                                     the own subfolder (the filename) within the downloads folder │
│ --input -i                          File/folder with URL(s) to download (non recursive)          │
│ --config-file --config -c           YAML file to use as config                                   │
│ --cache-file                        JSON file to use as cache                                    │
│ --database-file --db                SQLite file to use as database                               │
│ --cookies                           File/folder to import cookies from (.txt Netscape files)     │
│ --deep-scrape --no-deep-scrape      Make additional requests while scraping (slower)             │
│                                     [default: False]                                             │
│ --delete-empty-folders              Delete empty files and folders after a run                   │
│   --no-delete-empty-folders         [default: True]                                              │
│ --delete-partial-files              Delete partial files after a run                             │
│   --no-delete-partial-files         [default: False]                                             │
│ --download-folder --output -o -d    Base output path for all downloads                           │
│                                     [default: downloads/cyberdrop-dl]                            │
│ --dump-json -j --no-dump-json       Save details about each file (both skipped and downloaded)   │
│                                     to a .jsonl file                                             │
│                                     [default: False]                                             │
│ --ignore-history                    Download files even if the already are marked as downloaded  │
│   --no-ignore-history               on the database                                              │
│                                     [default: False]                                             │
│ --ignore-hashes --no-ignore-hashes  Download files even if their hash matches a file downloaded  │
│                                     on the database                                              │
│                                     [default: False]                                             │
│ --max-file-name-length              Max number of characters a filename should have. Filenames   │
│                                     longer that this will be truncated                           │
│                                     [default: 95]                                                │
│ --max-folder-name-length            Max number of characters a folder should have. Filenames     │
│                                     longer that this will be truncated                           │
│                                     [default: 60]                                                │
│ --max-thread-depth                  Restricts how many levels of nested threads are scraped on a │
│                                     forum                                                        │
│                                     [default: 0]                                                 │
│ --max-thread-folder-depth           Max number of nested folders CDL will create when            │
│                                     maximum_thread_depth is greater that 0                       │
│ --min-free-space                    Minimum free space require to start new downloads            │
│                                     [default: 5368709120]                                        │
│ --mtime --no-mtime                  Use original upload date as modification date for downloaded │
│                                     file                                                         │
│                                     [default: True]                                              │
│ --restrict-path                     [choices: unix, windows, no_emoji, ascii]                    │
│   --restrict-filenames              [default: ()]                                                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Crawlers ───────────────────────────────────────────────────────────────────────────────────────╮
│ --crawlers.disabled                  Name of crawlers to disable for the current run             │
│                                      [default: {}]                                               │
│ --crawlers.bandcamp.formats          Format to choose for downloads (if available), ordered by   │
│                                      preference                                                  │
│                                      [choices: mp3-320, mp3, aac-hi, wav, flac, vorbis, aiff,    │
│                                      alas]                                                       │
│                                      [default: ('mp3-320', 'mp3', 'aac-hi', 'wav', 'flac',       │
│                                      'vorbis', 'aiff', 'alas')]                                  │
│ --crawlers.clonr.use-source          Ignore files in clone and process the original Mega.nz URL  │
│   --crawlers.clonr.no-use-source     [default: False]                                            │
│ --crawlers.clonr.zip                 Download entire clone as a single ZIP file                  │
│   --crawlers.clonr.no-zip            [default: False]                                            │
│ --crawlers.clypit.prefer-mp3         Download audios as .mp3 files even if WAV (high quality)    │
│   --crawlers.clypit.no-prefer-mp3    versions are available                                      │
│                                      [default: False]                                            │
│ --crawlers.generic.wordpress-media   [default: ()]                                               │
│ --crawlers.generic.wordpress-html    [default: ()]                                               │
│ --crawlers.generic.discourse         [default: ()]                                               │
│ --crawlers.generic.chevereto         [default: ()]                                               │
│ --crawlers.generic.kvs               [default: ()]                                               │
│ --crawlers.generic.video             [default: ()]                                               │
│ --crawlers.generic.peertube          [default: ()]                                               │
│ --crawlers.google-drive.default-for  Default format for documents (can be overridden per URL     │
│   mats.docs                          with the 'format' query param)                              │
│                                      [choices: docx, odt, rtf, txt, epub, pdf, md, zip]          │
│                                      [default: docx]                                             │
│ --crawlers.google-drive.default-for  Default format for spreedsheets (can be overridden per URL  │
│   mats.sheets                        with the 'format' query param)                              │
│                                      [choices: xslx, ods, html, csv, tsv]                        │
│                                      [default: xslx]                                             │
│ --crawlers.google-drive.default-for  Default format for presentations (can be overridden per URL │
│   mats.slides                        with the 'format' query param)                              │
│                                      [choices: pptx, odp]                                        │
│                                      [default: pptx]                                             │
│ --crawlers.octave-music.quality      Quality of audio file to download (lossless are .flac       │
│                                      files)                                                      │
│                                      [choices: lossless, mp3-320]                                │
│                                      [default: mp3-320]                                          │
│ --crawlers.octave-music.filename-fo  Format to generate audio file                               │
│   rmat                               [default: {artist} - {title}{ext}]                          │
│ --crawlers.one-pace.prefer-dub       Download episodes with english audio tracks instead of      │
│   --crawlers.one-pace.no-prefer-dub  japanese (if available)                                     │
│                                      [default: False]                                            │
│ --crawlers.only-haven.file           Download the main file in a post (if any)                   │
│   --crawlers.only-haven.no-file      [default: True]                                             │
│ --crawlers.only-haven.attachments -  Download all attachments in a post (may or may not include  │
│   -crawlers.only-haven.no-attachmen  `file`)                                                     │
│   ts                                 [default: True]                                             │
│ --crawlers.only-haven.content-urls   Download any URL found inside the description (text) of a   │
│   --crawlers.only-haven.no-content-  post (slower)                                               │
│   urls                               [default: True]                                             │
│ --crawlers.only-haven.embed          Download the embedded file from third party sites (if       │
│   --crawlers.only-haven.no-embed     any)(mega.nz, pcloud, dropbox, etc..)                       │
│                                      [default: True]                                             │
│ --crawlers.pawchive.file             Download the main file in a post (if any)                   │
│   --crawlers.pawchive.no-file        [default: True]                                             │
│ --crawlers.pawchive.attachments      Download all attachments in a post (may or may not include  │
│   --crawlers.pawchive.no-attachment  `file`)                                                     │
│   s                                  [default: True]                                             │
│ --crawlers.pawchive.content-urls     Download any URL found inside the description (text) of a   │
│   --crawlers.pawchive.no-content-ur  post (slower)                                               │
│   ls                                 [default: True]                                             │
│ --crawlers.pawchive.embed            Download the embedded file from third party sites (if       │
│   --crawlers.pawchive.no-embed       any)(mega.nz, pcloud, dropbox, etc..)                       │
│                                      [default: True]                                             │
│ --crawlers.pornhub.profile-paths     Subpaths to scrape when an input URL is a profile's         │
│                                      homepage                                                    │
│                                      [default: ('photos/public', 'gifs/public', 'videos',        │
│                                      'videos/upload')]                                           │
│ --crawlers.tiktok.original           Download videos in original quality (slower)                │
│   --crawlers.tiktok.no-original      [default: False]                                            │
│ --crawlers.twitter.cards             Parse and download cards in a post (embeds from thirdparty  │
│   --crawlers.twitter.no-cards        sites)                                                      │
│                                      [default: True]                                             │
│ --crawlers.twitter.threads           Downloads all posts in a thread (All direct replies from OP │
│   --crawlers.twitter.no-threads      to their own tweet)                                         │
│                                      [default: True]                                             │
│ --crawlers.twitter.content-urls      Parse and try to download any URL found inside the text of  │
│   --crawlers.twitter.no-content-url  a tweet                                                     │
│   s                                  [default: True]                                             │
│ --crawlers.twitter.articles.cover -  Download the cover image of articles                        │
│   -crawlers.twitter.articles.no-cov  [default: True]                                             │
│   er                                                                                             │
│ --crawlers.twitter.articles.media -  Download media files in the body of articles                │
│   -crawlers.twitter.articles.no-med  [default: True]                                             │
│   ia                                                                                             │
│ --crawlers.twitter.retweets          Download media from retweets in the user's timeline         │
│   --crawlers.twitter.no-retweets     [default: False]                                            │
│ --crawlers.twitter.image-size        [choices: orig, 4096x4096, large, medium, small, thumb]     │
│                                      [default: orig]                                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Downloads ──────────────────────────────────────────────────────────────────────────────────────╮
│ --downloads                         Max number of files to download simultaneously               │
│                                     [default: 15]                                                │
│ --downloads.per-domain              Max number of files to download simultaneously per domain    │
│                                     [default: 5]                                                 │
│ --attempts                          [default: 2]                                                 │
│ --delay                             Number of seconds to wait before starting downloads          │
│                                     [default: 0.0]                                               │
│ --slow-speed                        Skip downloads if their speed is below this value for more   │
│                                     than 10 seconds. Set to 0 to disable                         │
│                                     [default: 0]                                                 │
│ --speed-limit                       Max speed rate (in bytes per second) to limit downloads      │
│                                     (combined)                                                   │
│                                     [default: 0]                                                 │
│ --back-pressure --no-back-pressure  Throttle scrape requests if there are too many downloads     │
│                                     queued for the same site                                     │
│                                     [default: True]                                              │
│ --jitter                            Wait a random additional number of seconds in between 0 and  │
│                                     <jitter> before downloads                                    │
│                                     [default: 0]                                                 │
│ --skip-and-mark-completed           Skip all downloads and mark them as downloaded on the        │
│   --no-skip-and-mark-completed      database                                                     │
│                                     [default: False]                                             │
│ --concurrent-segments               Allow up to `<N>` HLS segments to be downloaded concurrently │
│                                     [default: 10]                                                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Filters ────────────────────────────────────────────────────────────────────────────────────────╮
│ --audio --no-audio                   Download/skip audio files                                   │
│                                      [default: True]                                             │
│ --images --no-images                 Download/skip image files                                   │
│                                      [default: True]                                             │
│ --videos --no-videos                 Download/skip videos                                        │
│                                      [default: True]                                             │
│ --non-media --no-non-media           Download/skip non media files (.txt, zip, .rar, etc...)     │
│                                      [default: True]                                             │
│ --thumbnails --no-thumbnails         Download/skip thumbnails of media files (if available)      │
│                                      [default: False]                                            │
│ --image.size.min                                                                                 │
│ --image.size.max                                                                                 │
│ --video.size.min                                                                                 │
│ --video.size.max                                                                                 │
│ --audio.size.min                                                                                 │
│ --audio.size.max                                                                                 │
│ --non_media.size.min                                                                             │
│ --non_media.size.max                                                                             │
│ --video.duration.min                                                                             │
│ --video.duration.max                                                                             │
│ --audio.duration.min                                                                             │
│ --audio.duration.max                                                                             │
│ --before                             Only download files uploaded before this date               │
│ --after                              Only download files uploaded after this date                │
│ --filename-regex                     Only download files that match this regex                   │
│ --filename-regex-exclude             Do NOT download files that match this regex                 │
│ --only-hosts                         Only scrape/download from these domains                     │
│                                      [default: {}]                                               │
│ --skip-hosts                         Skip scrape/download from these domains                     │
│                                      [default: {}]                                               │
│ --allow-files-with-no-extension      Download potentially dangerous files that have no extension │
│   --no-allow-files-with-no-extensio  [default: False]                                            │
│   n                                                                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Hashing ────────────────────────────────────────────────────────────────────────────────────────╮
│ --hashing                            [choices: off, in-place, post-download]                     │
│                                      [default: in-place]                                         │
│ --hashing.algorithms --hashes        List of hashes to compute for each download                 │
│                                      [choices: xxh128, md5, sha256]                              │
│                                      [default: ('xxh128', 'md5', 'sha256')]                      │
│ --hashing.dedupe.enabled --dedupe    Auto delete duplicate downloads by hash                     │
│   --dedupe.enabled --auto-dedupe     [default: True]                                             │
│   --hashing.dedupe.no-enabled                                                                    │
│   --no-dedupe --dedupe.no-enabled                                                                │
│   --no-auto-dedupe                                                                               │
│ --hashing.dedupe.use-trash-bin       Send deleted files to the trash bin                         │
│   --hashing.dedupe.no-use-trash-bin  [default: True]                                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Jdownloader ────────────────────────────────────────────────────────────────────────────────────╮
│ --jdownloader.enabled --jdownloader  Send unsupported URLs to Jdownloader                        │
│   --jdownloader.no-enabled           [default: False]                                            │
│   --no-jdownloader                                                                               │
│ --jdownloader.deprecated-api         HTTP URL of a local JDownloader instance to connect to via  │
│                                      their deprecated API (insecure, default port=3128)          │
│ --jdownloader.autostart              Immediately start downloads as soon as they are sent        │
│   --jdownloader.no-autostart         [default: False]                                            │
│ --jdownloader.download-folder        Output path for Jdownloader. Defaults to                    │
│                                      `--download-folder`                                         │
│ --jdownloader.whitelist              Only send unsupported URLs from these domains to            │
│                                      Jdownloader. An empty list means 'send all URLs'            │
│                                      [default: {}]                                               │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Logs ───────────────────────────────────────────────────────────────────────────────────────────╮
│ --logs.level                         Only log messages of this level or higher to the main log   │
│                                      file                                                        │
│                                      [choices: DEBUG, INFO, WARNING, ERROR, CRITICAL]            │
│                                      [default: DEBUG]                                            │
│ --logs.console-level                 Only log messages of this level or higher to the console.   │
│                                      An empty or `None` value will use the same level as         │
│                                      `log_level`                                                 │
│ --logs.http-traffic --print-traffic  Log HTTP requests and responses (at INFO level)             │
│   --logs.no-http-traffic             [default: True]                                             │
│   --no-print-traffic                                                                             │
│ --logs.files.main --log-file         Path of main log file                                       │
│                                      [default: downloader.log]                                   │
│ --logs.files.download-errors         Save download errors to this file (MUST BE .csv)            │
│                                      [default: download_errors.csv]                              │
│ --logs.files.scrape-errors           Save scrape errors to this file (MUST BE .csv)              │
│                                      [default: scrape_errors.csv]                                │
│ --logs.files.unsupported             Save unsupported URLs to this file (MUST BE .csv)           │
│                                      [default: unsupported.csv]                                  │
│ --logs.files.last-forum-post         Save the URL of the last scraped post from each thread to   │
│                                      this file (MUST BE .csv)                                    │
│                                      [default: last_forum_post.csv]                              │
│ --logs.folder                        Base folder to prepend to log files paths (if they are not  │
│                                      absolute)                                                   │
│ --logs.expire-after                  Delete all log files inside `--logs.folder` if they are     │
│                                      older that this                                             │
│ --logs.rotate --logs.no-rotate       Append current datetimme to every log file on each run      │
│                                      [default: False]                                            │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ MaxChildren ────────────────────────────────────────────────────────────────────────────────────╮
│ --max-children.forum       Do not scrape more that this number of URLs inside a forum thread     │
│                            [default: 0]                                                          │
│ --max-children.forum-post  Do not scrape more that this number of URLs inside an individual a    │
│                            forum post                                                            │
│                            [default: 0]                                                          │
│ --max-children.profile     Do not scrape more that this number of URLs in a profile              │
│                            [default: 0]                                                          │
│ --max-children.album       Do not scrape more that this number of URLs in a album                │
│                            [default: 0]                                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Network ────────────────────────────────────────────────────────────────────────────────────────╮
│ --dump-responses                     Save text/HTML/JSON responses to disk (Flaresolverr         │
│   --no-dump-responses                responses are excluded)                                     │
│                                      [default: False]                                            │
│ --flaresolverr                       HTTP URL of an existing Flaresolverr instance               │
│ --flaresolverr-use-session           Create a custom session before making any request with      │
│   --no-flaresolverr-use-session      Flaresolverr                                                │
│                                      [default: True]                                             │
│ --flaresolverr-wait                  Force Flaresolverr to wait (at least) this number of        │
│                                      seconds before returning the results, to allow dynamic      │
│                                      content to load                                             │
│                                      [default: 0]                                                │
│ --flaresolverr-concurrency           Number of concurrent requests to make with Flaresolverr     │
│                                      [default: 1]                                                │
│ --proxy --http-proxy                 HTTP/HTTPS proxy                                            │
│ --rate-limit                         Max number of requests per second (only used while          │
│                                      scraping)                                                   │
│                                      [default: 25]                                               │
│ --connection-timeout                 [default: 15]                                               │
│ --read-timeout                       [default: 300]                                              │
│ --ssl-context                        [default: truststore+certifi]                               │
│ --verify --ssl --no-verify --no-ssl  [default: True]                                             │
│ --tls.min-version                    [choices: 1.2, 1.3]                                         │
│                                      [default: 1.2]                                              │
│ --ca-certs                           [default: ()]                                               │
│ --user-agent                         [default: Mozilla/5.0 (X11; Linux x86_64; rv:153.0)         │
│                                      Gecko/20100101 Firefox/153.0]                               │
│ --impersonate                        Use this target as impersonation for all scrape requests    │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Sort ───────────────────────────────────────────────────────────────────────────────────────────╮
│ --sort.enabled --sort          Enable/Disable file sorting at the end of a run                   │
│   --sort.no-enabled --no-sort  [default: False]                                                  │
│ --sort.input-folder            Base folder to scan for files. Default to the same value as       │
│                                `--download-folder`                                               │
│ --sort.output-folder           Output path to place sorted files in                              │
│                                [default: downloads/cyberdrop-dl sorted]                          │
│ --sort.formats.audio           Format to generate sorted audio file                              │
│                                [default: {sort_dir}/{base_dir}/Audio/{filename}{ext}]            │
│ --sort.formats.image           Format to generate sorted image file                              │
│                                [default: {sort_dir}/{base_dir}/Images/{filename}{ext}]           │
│ --sort.formats.non-media       Format to generate sorted files of unknown type                   │
│                                [default: {sort_dir}/{base_dir}/Other/{filename}{ext}]            │
│ --sort.formats.video           Format to generate sorted video file                              │
│                                [default: {sort_dir}/{base_dir}/Videos/{filename}{ext}]           │
│ --sort.formats.incrementer     Format for separator on name collisions                           │
│                                [default:  ({i})]                                                 │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ SubFolders ─────────────────────────────────────────────────────────────────────────────────────╮
│ --subfolders.create --subfolders     Enable/disable the createtion of nested sub-folders         │
│   --subfolders.no-create             [default: True]                                             │
│   --no-subfolders                                                                                │
│ --subfolders.include.album-id        [default: False]                                            │
│   --subfolders.include.no-album-id                                                               │
│ --subfolders.include.thread-id       [default: False]                                            │
│   --subfolders.include.no-thread-id                                                              │
│ --subfolders.include.domain          [default: True]                                             │
│   --subfolders.include.no-domain                                                                 │
│ --subfolders.separate-posts.format   [default: {default}]                                        │
│ --subfolders.enabled                 Create new subfolders for every post on a site              │
│   --separate-posts                   [default: False]                                            │
│   --separate-posts.enabled                                                                       │
│   --subfolders.no-enabled                                                                        │
│   --no-separate-posts                                                                            │
│   --separate-posts.no-enabled                                                                    │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ UIOptions ──────────────────────────────────────────────────────────────────────────────────────╮
│ --ui                      [choices: disabled, activity, simple, fullscreen]                      │
│                           [default: fullscreen]                                                  │
│ --portrait --no-portrait  force CDL to run with a vertical layout                                │
│                           [default: False]                                                       │
│ --refresh-rate            [default: 10.0]                                                        │
│ --stats --no-stats        Show stats report at the end of a run                                  │
│                           [default: True]                                                        │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯

Github:      https://github.com/Cyberdrop-DL/cyberdrop-dl
Wiki (docs): https://script-ware.gitbook.io/cyberdrop-dl
```
<!-- END_CLI_OVERVIEW -->
