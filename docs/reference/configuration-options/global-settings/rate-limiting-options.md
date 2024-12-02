---
description: These are limiting options for the program
---
# Rate Limiting Options

## `connection_timeout`

The number of seconds to wait while connecting to a website before timing out.


## `download_attempts`

The number of download attempts per file. Regardless of this value, some conditions (such as a 404 HTTP status) will cause a file to not be retried at all.

## `read_timeout`

The number of seconds to wait while reading data from a website before timing out. If it's a download, it will be retried and won't count against the download_attempts limit.

## `rate_limit`

This is the maximum number of requests that can be made by the program per second.

## `download_delay`

This is the number of seconds to wait between downloads to the same domain.

Some domains have internal limits set by the program, such as `bunkrr`, `cyberfile.me`, etc.

## `max_simultaneous_downloads`

This is the maximum number of files that can be downloaded simultaneously.

## `max_simultaneous_downloads_per_domain`

This is the maximum number of files that can be downloaded from a single domain simultaneously.

Some domains have internal limits set by the program, such as `bunkrr`, `cyberfile.me`, etc.

## `download_speed_limit`

This is the max rate of downloading in KB for all downloads combined
Set to `0` or `null` to disable
