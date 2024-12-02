# Dupe Cleanup Options

These are options for enable/disable hashing and auto dupe delection

To enable auto dupe cleanup:

1. Set `hashing` to `IN_PLACE` or `POST_DOWNLOAD`
2. Set `auto_dedupe` to `true`



## hashing
There are three possible options for hashing

1. `OFF`: disables hashing
2. `IN_PLACE`: performs hashing after each download
3. `POST_DOWNLOAD`: performs hashing after all downloads have completed

The default hasing algorithm is `xxh128`. You can enable aditional hashing algoritms, but you can not replace the default



## auto_dedupe

Enables deduping files functionality. Needs `hashing` to be enabled

This finds all files in the database with the same hash and size, and keeps the oldest copy of the file

Deletion only occurs if two or more matching files are found from the database search



## add_sha256_hash

allows files to be hashed with the `sha256` algorithm, this enables matching with sites that provide this information



## add_md5_hash

allows files to be hash with the `md5` algorithm, this enables matching with sites that provide this information.

{% hint style="info" %}
**md5** was de default hashing algoritm of cyberdrop-dl v5. If you have a database from v5 that you would like to import into v6, is recommend to enable `md5` to match previous hashed files
{% endhint %}



## send_deleted_to_trash

files are sent to trash instead of permanently deleting, enabling easy restoration
