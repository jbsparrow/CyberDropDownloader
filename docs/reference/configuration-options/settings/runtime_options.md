# Runtime Options

These are higher level options that effect the overarching functions of the program.

## `console_log_level`

| Type             | Default |
| ---------------- | ------- |
| `NonNegativeInt` | `100`   |

Same as `log_level` but it controls which messages are shown on the console.

{% hint style="info" %}
This option is ignored unless CDL is running with `--no-ui`
{% endhint %}

## `deep_scrape`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

Cyberdrop-DL uses a some tricks to try to reduce the number of requests it needs to make while scraping a site. However, this may cause a few links to be skipped. Use `--deep-scrape` to disable this functionality and always make a new request.

This setting is temporary and will always reset to `false` after each run

{% hint style="warning" %}
Use this option only when absolutely necessary, as it will significantly increase the number of requests being made.

For example, scraping an album normally takes one single request. However, with `--deep-scrape`, CDL will make `n` requests per album, where `n` is the total number of items in the album
{% endhint %}

## `delete_partial_files`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

The program will leave partial files alone as they will be used to resume downloads on subsequent runs.

Setting this to `true` will remove any partial downloads from the download folder.

## `ignore_history`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

By default, the program tracks your downloads to prevent downloading the same files multiple times, helping to save time and reduce strain on the servers you're downloading from.

Setting this to `true` will cause the program to ignore the history, and will allow you to re-download files.

## `jdownloader_autostart`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

Setting this to `true` will make jdownloader start downloads as soon as they are sent.

This option has no effect unless `send_unsupported_to_jdownloader` is `true`

## `jdownloader_download_dir`

| Type             | Default |
| ---------------- | ------- |
| `Path` or `null` | `null`  |

The `download_dir` jdownloader will use. A `null` value (the default) will make jdownloader use the same `download_dir` as Cyberdrop-DL. Use this option as path mapping when jdownloader is running on a different host / docker.

This option has no effect unless `send_unsupported_to_jdownloader` is `true`

## `jdownloader_whitelist`

| Type                | Default |
| ------------------- | ------- |
| `list[NonEmptyStr]` | `[]`    |

List of domain names. An unsupported URL will only be sent to jdownloader if its host is found on the list. An empty whitelist (the default) will disable this functionality, sending any unsupported URL to jdownloader

This option has no effect unless `send_unsupported_to_jdownloader` is `true`

## `log_level`

| Type             | Default |
| ---------------- | ------- |
| `NonNegativeInt` | `10`    |

Defines the logging level for messages, according to [Python logging levels](https://docs.python.org/3/library/logging.html#levels). Only messages with a level equal or greater than this setting will be logged, with the exception of `NOTSET` which will disable all logging messages. Setting a value above 50 will also disable logging entirely.

| Level      | Value | Description                                                                                                    |
| ---------- | ----- | -------------------------------------------------------------------------------------------------------------- |
| `NOTSET`   | 0     | Disables all log messages                                                                                      |
| `DEBUG`    | 10    | Offers detailed information, typically useful to troubleshoot problems                                         |
| `INFO`     | 20    | Provides general information about scrape and download progress                                                |
| `WARNING`  | 30    | Highlights a potential issue or something that might need attention (e.g. `Login wasn't provided for <FORUM>`) |
| `ERROR`    | 40    | Denotes a serious problem preventing Cyberdrop-DL to execute some function                                     |
| `CRITICAL` | 50    | Fatal error that causes Cyberdrop-DL to exit immediately                                                       |

{% hint style="info" %}
Using anything other that `DEBUG` makes troubleshooting issues harder. Practically speaking, this should only be adjusted if you expect CDL to run for an extended period (with a large number of input URLs) to minimize the log files sizes
{% endhint %}

## `send_unsupported_to_jdownloader`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

Cyberdrop-DL has integration with jdownloader. This will allow you to download URLs that Cyberdrop-DL finds but do not support. However, this setting is disabled by default.

Setting this to `true`, will send unsupported links over.

## `skip_check_for_empty_folders`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

After a run is complete, the program will do a check (and remove) any empty files and folders in the download and scan folder.

Setting this to `true` will disable this functionality.

## `skip_check_for_partial_files`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

After a run is complete, the program will do a check to see if any partially downloaded files remain in the downloads folder and will notify you of them.

Setting this to `true` will skip this check.

## `slow_download_speed`

| Type       | Default |
| ---------- | ------- |
| `ByteSize` | `0`     |

{% hint style="info" %}
This setting specifies speed and it's interpreted as `<value> / second`. ex: `8MB` means `8MB/s`
{% endhint %}

Downloads with a speed lower than this value for more than 10 seconds will be skipped. Set to `0` to disable

## `update_last_forum_post`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

Updates `input_file` content, adding the last scraped post id to every forum thread URL
