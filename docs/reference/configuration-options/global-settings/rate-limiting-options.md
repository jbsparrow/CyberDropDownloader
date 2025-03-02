---
description: These are limiting options for the program
---
# Rate Limiting Options

## `connection_timeout`

| Type          | Default |
| ------------- | ------- |
| `PositiveInt` | `15`    |

The number of seconds to wait while connecting to a website before timing out

{% hint style="info" %} This value will also be used for Flaresolverr (if enabled) as the max number of seconds to solve a CAPTCHA challenge {% endhint %}


## `download_attempts`

| Type          | Default |
| ------------- | ------- |
| `PositiveInt` | `5`     |

The number of download attempts per file. Regardless of this value, some conditions (such as a 404 HTTP status) will cause a file to not be retried at all.

## `download_delay`

| Type               | Default |
| ------------------ | ------- |
| `NonNegativeFloat` | `0.5`   |

This is the number of seconds to wait between downloads to the same domain.

Some domains have internal limits set by the program, which can not be modified:

- `bunkrr`: 1
- `cyberfile.me`: 1
- `pixeldrain` : 2

## `download_speed_limit`

| Type       | Default |
| ---------- | ------- |
| `ByteSize` | `0`     |

{% hint style="info" %}
This setting specifies speed and it's interpreted as `<value> / second`. ex: `8MB` means `8MB/s`
{% endhint %}

This is the max rate of downloading in bytes (per second) for all downloads combined. Set to `0` to disable

## `file_host_cache_expire_after`

| Type                        | Default  |
| --------------------------- | -------- |
| `timedelta`, `str` or `int` | `7 days` |

Cyberdrop-DL caches the requests made to any website. This setting controls how long responses to file host websites are stored before expiring.

- A `timedelta` input is expected to be a valid ISO 8601 timespan, ex: `P10DT2H30M10S`

- An `int` input is assumed to be the number of days

- A  `str` input is expected to be in the format; `<value> <unit>`, ex: `10 days`.

### Valid `str` units

- `year(s)`
- `month(s)`
- `week(s)`
- `day(s)`
- `hour(s)`
- `minute(s)`
- `second(s)`
- `millisecond(s)`
- `microsecond(s)`

{% hint style="info" %}
You can set the value to `0` to disable caching
{% endhint %}

## `forum_cache_expire_after`

| Type                        | Default   |
| --------------------------- | --------- |
| `timedelta`, `str` or `int` | `4 weeks` |

Same as `file_host_cache_expire_after` but applied to forums requests.

## `max_simultaneous_downloads`

| Type          | Default |
| ------------- | ------- |
| `PositiveInt` | `15`    |

This is the maximum number of files that can be downloaded simultaneously.

## `max_simultaneous_downloads_per_domain`

| Type          | Default |
| ------------- | ------- |
| `PositiveInt` | `3`     |

This is the maximum number of files that can be downloaded from a single domain simultaneously.

Some domains have internal limits set by the program, such as `bunkrr`, `cyberfile.me`, etc.

## `rate_limit`

| Type          | Default |
| ------------- | ------- |
| `PositiveInt` | `50`    |

{% hint style="info" %}
This setting specifies speed and it's interpreted as `<value> / second`. ex: `50` means `50 requests / second`
{% endhint %}

This is the maximum number of requests that can be made by the program per second.

## `read_timeout`

| Type          | Default |
| ------------- | ------- |
| `PositiveInt` | `300`   |

The number of seconds to wait while reading data from a website before timing out. If it's a download, it will be retried and won't count against the `download_attempts` limit.
