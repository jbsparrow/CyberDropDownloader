# Logs

## `log_folder`

| Type           | Default  |
|----------------|----------|
| `Path` | `AppData/Configs/{config}/Logs` |

The path to the location you want Cyberdrop-DL to store logs in.

## `main_log`

| Type           | Default  | Restrictions |
|----------------|----------| ------------ |
| `Path` | `downloader.log` | extension will always be overridden to `.log` |

Path of main log file. For relative paths, the final path will be `log_folder` / `main_log`

## `last_forum_post`

| Type           | Default  | Restrictions |
|----------------|----------| ------------ |
| `Path` | `Last_Scraped_Forum_Posts.csv` | extension will always be overridden to `.csv` |

Path of the forum-post log file. For relative paths, the final path will be `log_folder` / `last_forum_post`

Cyberdrop-DL will store the link to the last forum posts it scraped from a given forum thread in this file.

## `unsupported_urls`

| Type           | Default  | Restrictions |
|----------------|----------| ------------ |
| `Path` | `Unsupported_URLs.csv` | extension will always be overridden to `.csv` |

Path of the unsupported log file. For relative paths, the final path will be `log_folder` / `unsupported_urls`

Cyberdrop-DL will output links it can't download to this file.

## `download_error_urls`

| Type           | Default  | Restrictions |
|----------------|----------| ------------ |
| `Path` | `Download_Error_URLs.csv` | extension will always be overridden to `.csv` |

Path of the download error log. For relative paths, the final path will be `log_folder` / `download_error_urls`

Cyberdrop-DL will output the links it fails to download, the reason and their origin in CSV format.

## `scrape_error_urls`

| Type           | Default  | Restrictions |
|----------------|----------| ------------ |
| `Path` | `Scrape_Error_URLs.csv` | extension will always be overridden to `.csv` |

What you want Cyberdrop-DL to call the scrape error log. For relative paths, the final path will be `log_folder` / `scrape_error_urls`

Cyberdrop-DL will output the links it fails to scrape, the reason and their origin in CSV format.

## `webhook`

| Type           | Default  | Restrictions |
|----------------|----------| ------------ |
| `AppriseURL` or `null` | `null` | The scheme of the URL must be `http` or `https` |

The URL of a webhook that you want to send download stats to (Ex: Discord). You can add the optional tag `attach_logs=` as a prefix to include a copy of the main log as an attachment.

Example:

> `attach_logs=https://discord.com/api/webhooks/webhook_id/webhook_token`

## `rotate_logs`

| Type           | Default  |
|----------------|----------|
| `bool` | `false`|

If enabled, Cyberdrop-DL will add the current date and time as a suffix to each log file, in the format `YYMMDD_HHMMSS`

Every log file will be created inside a sub folder with the current date

This will prevent overriding old log files



## `logs_expire_after`

| Type              | Default  |
|-------------------|----------|
| `timedelta` or `null`| `null`|

With `rotate_logs` enabled, this setting specifies the retention period for log files before they are deleted

- A `timedelta` input is expected to be a valid ISO 8601 timespan, ex: `P10DT2H30M10S`
- An `int` input is assumed to be the number of days
- A  `str` input is expected to be in the format; `<value> <unit>`, ex: `10 days`.
- A `null` value will disable automatic delection of logs


{% hint style="warning" %}
Any `.log` or `.csv` file within `log_folder` will be deleted, even if CDL did not create them
{% endhint %}

{% hint style="info" %}
Log files with an absolute path not relative to `log_folder` will never be deleted
{% endhint %}



## `log_line_width`

| Type           | Default  | Restrictions |
|----------------|----------|--------------|
| `PositiveInt` | `240`| `>=50`|

Line width to use when writing to the main log file
