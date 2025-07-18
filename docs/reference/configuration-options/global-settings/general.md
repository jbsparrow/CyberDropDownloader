---
description: These are some general settings that will be used regardless of which config is loaded
---
# General

## `disable_crawlers`

| Type                | Default | Additional Info                                                      |
| ------------------- | ------- | -------------------------------------------------------------------- |
| `list[NonEmptyStr]` | `[]`    | This is an [`AdditiveArg`](../special_setting_types.md#additiveargs) |

You can supply a list of crawlers to disable for the current run. This will make CDL completely ignore the crawler, as if the site was not supported. However, links from the site will still be processed by Real-Debrid (if enabled), Jdownloader (If enabled) and the Generic crawler (If enabled), in that order.

The list should be valid crawlers names. The name of the crawler is the name of the primary site they support. ex: `4Chan`, `Bunkrr`, `Dropbox`
Crawlers names correspond to the column `site` in the [supported sites page](https://script-ware.gitbook.io/cyberdrop-dl/reference/supported-websites#supported-sites).

## `enable_generic_crawler`

| Type   | Default |
| ------ | ------- |
| `bool` | `true`  |

CDl has a generic crawler that will try to download from unsupported sites. Setting this to `false` will disable it.

{% hint style="info" %}
CDL will still try to download from unsupported URLs if the last part of the URL has a known file extension. ex: `.jpg`
{% endhint %}

## `flaresolverr`

| Type                | Default |
| ------------------- | ------- |
| `HttpURL` or `null` | `null`  |

[FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) is a proxy server to bypass Cloudflare and `DDoS-Guard` protection. The provided value must be a valid `http` URL of an existing flaresolverr instance. Ex: `http://192.168.1.44:4000`

{% hint style="info" %}
`0.0.0.0` is NOT a valid IP address. To set up a flaresolverr instance running on the same machine as CDL, use `127.0.0.1` as the IP
{% endhint %}

{% hint style="warning" %}
This wiki does not cover flaresolverr setup process. If you need help, refer to their documentation. Please do not open issues related to flaresolverr or `DDoS-Guard`.
See: [How to extract cookies (DDoSGuard or login errors) #839](https://github.com/jbsparrow/CyberDropDownloader/discussions/839) for alternatives using cookies
{% endhint %}

## `max_file_name_length`

| Type          | Default |
| ------------- | ------- |
| `PositiveInt` | `95`    |

This is the maximum number of characters filename should have. CDL will truncate filenames longer that this.

## `max_folder_name_length`

| Type          | Default |
| ------------- | ------- |
| `PositiveInt` | `95`    |

This is the maximum number of characters a folder should have. CDL will truncate folders longer that this.

## `proxy`

| Type                | Default |
| ------------------- | ------- |
| `HttpURL` or `null` | `null`  |

The proxy you want CDL to use. Only `http` proxies are supported. Ex: `https://user:password@ip:port`

## `required_free_space`

| Type       | Default | Restrictions |
| ---------- | ------- | ------------ |
| `ByteSize` | `5GB`   | `>=512MB`    |

This is the minimum amount of free space require to start new downloads.

{% hint style="info" %}
If you set a value lower than `512MB`, CDL will override it with `512MB`
{% endhint %}

## `ssl_context`

| Type                  | Default              |
| --------------------- | -------------------- |
| `NonEmptyStr` or None | `truststore+certifi` |

Context that will used to verify SSL connections. Valid values are:

- `truststore`: Will use certificates already included with the OS

- `certifi`: Will use certificates bundled with the `certifi` version available at the release of the current CDL version

- `truststore+certifi`: Will use certificates already included with the OS, with a fallback to `certifi` for missing certificates

- `None`: Will completly disable SSL verification, allowing secure connections.

Setting this to `None` will allow the program to connect to websites without SSL encryption (insecurely).

{% hint style="danger" %}
Sensitive data may be exposed using an insecure connection. For your safety, is recommended to always use a secure HTTPS connection.
{% endhint %}

## `user_agent`

| Type          | Default                                                                            |
| ------------- | ---------------------------------------------------------------------------------- |
| `NonEmptyStr` | `Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0` |

The user agent is the signature of your browser. Some sites use it to identify if the requests come from a human or a robot.
You can google "what is my user agent" to get yours.

{% hint style="info" %}
If you use flaresolverr, this value MUST match with flaresolverr's user agent. Otherwise, flaresolverr cookies won't work
{% endhint %}
