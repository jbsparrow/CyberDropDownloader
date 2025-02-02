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

The user agent is the signature of your browser, it's how it is represented to websites you connect to. You can google "what is my user agent" to see what yours may be.

{% hint style="info" %}
If you use flaresolverr, this value must match with flaresolverr user agent for its cookies to work
{% endhint %}
