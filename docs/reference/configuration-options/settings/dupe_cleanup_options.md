---
description: These are options for enable/disable hashing and auto dupe deletion
---
# Dupe Cleanup Options

Cyberdrop-DL maintains an internal database of all downloaded files, indexed by their hashes. This can be used to automatically delete newly downloaded files if they were downloaded before. To enable auto dupe cleanup:

1. Set `hashing` to `IN_PLACE` or `POST_DOWNLOAD`
2. Set `auto_dedupe` to `true`

## `hashing`

| Type           | Default  | Restrictions |
|----------------|----------| ----------- |
| `HASHING` | `OFF` | Must be `OFF`, `IN_PLACE` or `POST_DOWNLOAD`|

There are three possible options for hashing:

1. `OFF`: disables hashing
2. `IN_PLACE`: performs hashing after each download
3. `POST_DOWNLOAD`: performs hashing after all downloads have completed

The default hashing algorithm is `xxh128`. You can enable additional hashing algorithms, but you can not replace the default.

## `auto_dedupe`

| Type           | Default  |
|----------------|----------|
| `bool` | `false` |

Enables deduping files functionality. Needs `hashing` to be enabled

The auto_dedupe feature scans the database for files with matching hashes and sizes, automatically deleting any duplicates and retaining only the oldest copy.

Deletion will only occur if two or more matching files are found during the database search.

## `add_sha256_hash`

| Type           | Default  |
|----------------|----------|
| `bool` | `false` |

If enabled, calculates the `sha256` hash for every downloaded file and store it in the internal database. This allows the program to match files with sites that provide hash information before downloading them, skipping the download altogether if a match is found

## `add_md5_hash`

| Type           | Default  |
|----------------|----------|
| `bool` | `false` |

If enabled, calculates the `md5` hash for every downloaded file and store it in the internal database. This allows the program to match files with sites that provide hash information before downloading them, skipping the download altogether if a match is found

{% hint style="warning" %}
`md5` was the default hashing algorithm of Cyberdrop-DL V5. If you have a V5 database that you'd like to import into V6, it's recommended to enable `md5` hashing to ensure new downloads match previously hashed files.
{% endhint %}

## `send_deleted_to_trash`

| Type           | Default  |
|----------------|----------|
| `bool` | `false` |

Deduped files are sent to the trash bin instead of being deleted
