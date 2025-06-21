---
description: These are some general settings that will be used regardless of which config is loaded
---
# General

## `allow_insecure_connections`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

Setting this to `true` will allow the program to connect to websites without SSL encryption (insecurely).

{% hint style="danger" %}
This will make the connection insecure, and sensitive data may be exposed. You should only enable this option if you know what you are doing. For your safety, is recommended to always use a secure HTTPS connection to protect your privacy.
{% endhint %}

## `disable_crawlers`

| Type                | Default | Additional Info                                                     |
| ------------------- | ------- | ------------------------------------------------------------------- |
| `list[NonEmptyStr]` | `[]`    | This is an [`AdditiveArg`](../special_setting_types.md#additiveargs) |

You can supply a list of crawlers to disable for the current run. This will make CDL completly ignore the crawler, as if the site was not supported. However, links from the site will still be proccesed by Real-Debrid (if enabled), Jdownloader (If enabled) and the Generic crawler (If enabled), in that order.

The list should be valid crawlers names. The name of the crawler if the name of the primary site they support. ex: `4Chan`, `Bunkrr`, `Dropbox`
Crawlers names correspond to the column `site` in the [supported sites page](https://script-ware.gitbook.io/cyberdrop-dl/reference/supported-websites#supported-sites).


## `enable_generic_crawler`

| Type   | Default |
| ------ | ------- |
| `bool` | `true` |

CDl has a generic crawler that will try to download from unsupported sites. Setting this to `false` will disable it.

{% hint style="info" %}
CDL will still try to download from unsupported URLs if the last part of the URL has a known file extension. ex: `.jpg`
{% endhint %}

## `flaresolverr`

| Type                | Default |
| ------------------- | ------- |
| `HttpURL` or `null` | `null`  |

[FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) is a proxy server to bypass Cloudflare and DDoS-GUARD protection. The provided value must be a valid `http` URL of an existing flaresolverr instance. Ex: `http://ip:port`

{% hint style="warning" %}
This wiki does not covert flaresolverr setup process. If you need help, refer to their documentation. Please refrain from opening issues related to flaresolverr.
{% endhint %}

## `max_file_name_length`

| Type          | Default |
| ------------- | ------- |
| `PositiveInt` | `95`    |

This is the maximum number of characters allowable in a filename.

## `max_folder_name_length`

| Type          | Default |
| ------------- | ------- |
| `PositiveInt` | `95`    |

This is the maximum number of characters allowable in a folder name.

## `pause_on_insufficient_space`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

Setting this to `true` will make CDL pause if there not enough free space available.

{% hint style="info" %}
CDL will only pause once. After the user resumes, every `InsufficientFreeSpaceError` will be propagated
{% endhint %}

## `proxy`

| Type                | Default |
| ------------------- | ------- |
| `HttpURL` or `null` | `null`  |

The proxy you want CDL to use. Only `http` proxies are supported. Ex: `https://user:pass@ip:port`

## `required_free_space`

| Type       | Default | Restrictions |
| ---------- | ------- | ------------ |
| `ByteSize` | `5GB`   | `>=512MB`    |

This is the minimum amount of free space require to start new downloads.

## `user_agent`

| Type          | Default                                                                            |
| ------------- | ---------------------------------------------------------------------------------- |
| `NonEmptyStr` | `Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0` |

The user agent is the signature of your browser, determining how it is presented to the websites you visit.. You can google "what is my user agent" to see what yours may be.

{% hint style="info" %}
If you use flaresolverr, this value must match with flaresolverr user agent for its cookies to work
{% endhint %}
