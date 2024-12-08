# Runtime Options

These are higher level options that effect the overarching functions of the program.

## `ignore_history`

| Type           | Default  |
|----------------|----------|
| `bool` | `false`|

By default, the program tracks your downloads to prevent downloading the same files multiple times, helping to save time and reduce strain on the servers you're downloading from.

Setting this to `true` will cause the program to ignore the history, and will allow you to re-download files.

## `skip_check_for_partial_files`


| Type           | Default  |
|----------------|----------|
| `bool` | `false`|

After a run is complete, the program will do a check to see if any partially downloaded files remain in the downloads folder and will notify you of them.

Setting this to `true` will skip this check.

## `skip_check_for_empty_folders`


| Type           | Default  |
|----------------|----------|
| `bool` | `false`|

After a run is complete, the program will do a check (and remove) any empty files and folders in the download and scan folder.

Setting this to `true` will disable this functionality.

## `delete_partial_files`


| Type           | Default  |
|----------------|----------|
| `bool` | `false`|

The program will leave partial files alone as they will be used to resume downloads on subsequent runs.

Setting this to `true` will remove any partial downloads from the download folder.

## `send_unsupported_to_jdownloader`


| Type           | Default  |
|----------------|----------|
| `bool` | `false`|

Cyberdrop-DL has integration with jdownloader. This will allow you to download URLs that Cyberdrop-DL finds but do not support. However, this setting is disabled by default.

Setting this to `true`, will send unsupported links over.

## `jdownloader_autostart`


| Type           | Default  |
|----------------|----------|
| `bool` | `false`|

Setting this to `true` will make jdownloader start downloads as soon as they are sent.

This option has no effect unless `send_unsupported_to_jdownloader` is `true`

## `jdownloader_download_dir`

| Type           | Default  |
|----------------|----------|
| `Path` or `null` | `null`|

The `download_dir` jdownloader will use. A `null` value (the default) will make jdownloader use the same `download_dir` as Cyberdrop-DL. Use this option as path mapping when jdownloader is running on a different host / docker.

This option has no effect unless `send_unsupported_to_jdownloader` is `true`

## `jdownloader_whitelist`

| Type           | Default  |
|----------------|----------|
| `list[NonEmptyStr]` | `[]`|

List of domain names. An unsupported URL will only be sent to jdownloader if its host is found on the list. An empty whitelist (the default) will disable this functionality, sending any unsupported URL to jdownloader

This option has no effect unless `send_unsupported_to_jdownloader` is `true`


## `update_last_forum_post`

| Type           | Default  |
|----------------|----------|
| `bool` | `false`|

Updates `input_file` content, adding the last scraped post id to every forum thread URL
