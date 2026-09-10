# `connection_timeout`

| Type          | Default |
| ------------- | ------- |
| `PositiveInt` | `15`    |

The number of seconds to wait while connecting to a website before timing out

{% hint style="info" %} This value will also be used for Flaresolverr (if enabled) as the max number of seconds to solve a challenge {% endhint %}

```yaml
network:
  connection_timeout: 15.0
```

# `rate_limit`

| Type            | Default |
| --------------- | ------- |
| `PositiveFloat` | `25.0`  |

This is the maximum number of requests that can be made by the program per second.

```yaml
network:
  rate_limit: 25.0
```

{% hint style="info" %}
This setting specifies speed and it's interpreted as `<value> / second`. ex: `25` means `25 requests / second`
{% endhint %}

{% hint style="info" %}
Rate limit is only taken into account while scraping, not for downloads
{% endhint %}

# `read_timeout`

| Type                      | Default |
| ------------------------- | ------- |
| `PositiveFloat` or `null` | `300.0` |

The number of seconds to wait while reading data from a website before timing out. A `null` value will make CDL keep the socket connection open indefinitely,
even if the server is not sending data anymore

```yaml
network:
  read_timeout: 300.0
```

# `flaresolverr`

| Type                | Default |
| ------------------- | ------- |
| `HttpURL` or `null` | `null`  |

[FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) is a proxy server to bypass Cloudflare and `DDoS-Guard` protection. The provided value must be a valid `http` URL of an existing flaresolverr instance. Ex: `http://192.168.1.44:4000`

```yaml
network:
  flaresolverr: null
```

{% hint style="info" %}
You can use any software with Flaresolverr like capabilities as long as it supports the `/v1` endpoint.

You may need to disable sessions with `flaresolverr_use_session`

{% endhint %}

{% hint style="info" %}
`0.0.0.0` is NOT a valid IP address. To set up a flaresolverr instance running on the same machine as CDL, use `127.0.0.1` as the IP
{% endhint %}

{% hint style="warning" %}
This wiki does not cover flaresolverr setup process. If you need help, refer to their documentation. Please do not open issues related to flaresolverr or `DDoS-Guard`.
See: [How to extract cookies (DDoSGuard or login errors) #839](https://github.com/Cyberdrop-DL/cyberdrop-dl/discussions/839) for alternatives using cookies
{% endhint %}

# `flaresolverr_use_session`

| Type   | Default |
| ------ | ------- |
| `bool` | `true`  |

Create a custom flaresolverr session that keeps cookies. This reduces the likelihood of CF challenges and speeds up requests since Flaresolverr won't
have to launch a new browser instance on every new one.

Set this to `false` if you are using other Flaresolverr like software that supports the `v1` endpoint but does not support the `sessions.create` command

# `flaresolverr_concurrency`

| Type          | Default |
| ------------- | ------- |
| `PositiveInt` | `1`     |

Number of concurrent requests to make with Flaresolverr

{% hint style="warning" %}
if `flaresolverr_use_session` is True, `flaresolverr_concurrency` **must be** 1. Sessions can only handle 1 request at a time.
{% endhint %}

# `flaresolverr_wait`

| Type             | Default |
| ---------------- | ------- |
| `NonNegativeInt` | `0`     |

Force Flaresolverr to wait (at least) this number of seconds before returning the results, to allow dynamic content to load.

Equivalent to the `waitInSeconds` param of the `request.get` command

# `proxy`

| Type                | Default |
| ------------------- | ------- |
| `HttpURL` or `null` | `null`  |

The proxy you want CDL to use. Only `http`/`https` proxies are supported. Ex: `https://user:password@ip:port`

```yaml
network:
  proxy: null
```

# `dump_responses`

| Type   | Default |
| ------ | ------- |
| `bool` | `False` |

CDL will save to disk a copy of every non binary request (text/HTML/JSON) as a single file. The files will be saved to a folder named `cdl_responses`, inside the parent folder of the main log file.

```yaml
network:
  dump_responses: false
```

{% hint style="info" %}
Flaresolverr responses are excluded. They are never dumped to disk
{% endhint %}

# `impersonate`

| Type                                                                             | Default |
| -------------------------------------------------------------------------------- | ------- |
| `chrome", "edge", "safari", "safari_ios", "chrome_android", "firefox"` or `null` | `null`  |

Impersonation allows CDL to make requests as a real web browser. This helps bypass bot-protection on some sites and it's required for any site that only accepts HTTP2 connections.

- The default value (`null`) means CDL will automatically use impersonation for crawlers that were programmed to use it.
- Passing an specific target (ex: `--impersonate chrome_android`) will make CDL use impersonation for all requests, using that tarjet

```yaml
network:
  impersonate: null
```

{% hint style="info" %}
The current default target is `chrome`. The default target can change on any new release without notice, even minor versions
{% endhint %}

# `tls`

## `verify`

| Type   | Default |
| ------ | ------- |
| `bool` | `True`  |

Enable/disable verification of SSL/TLS certificates for HTTP requests

{% hint style="danger" %}
Sensitive data may be exposed using an insecure connection. This option should only be disabled for troubleshooting connection errors.

If you have TLS connection problems with an site but you trust it, it's recommended to load its certificate chain (`.pem`) file
with the `ca-certs` option
{% endhint %}

## `ca_certs`

| Type         | Default |
| ------------ | ------- |
| `list[Path]` | `[]`    |

A list path to CA bundles to use in PEM format. All paths must exists.

If a path points to a file, it MUST have a `.pem` extension. If a path points to a folder, all `.pem` in it will be loaded (non recursive).

{% hint style="info" %}
These are **additional** certificates, they will be bundled with the certificates already present in your OS's default CA truststore
{% endhint %}

{% hint style="info" %}
`cyberdrop-dl` always include an additional bundle with the root certificates used by Mozilla, from the Common CA Database (<https://www.ccadb.org>).
This bundle is updated periodically on new versions. For details, see: <https://github.com/jawah/wassima>
{% endhint %}

## `min_version`

| Type           | Default |
| -------------- | ------- |
| `1.2` or `1.3` | `1.2`   |

Mininum TLS version to use. Using `1.3` may help with Cloudflare/DDoS-Guard errors and some fingerprint blocks

```yaml
tls:
  ca_certs: []
  min_version: "1.2"
  verify: true
```

# `user_agent`

| Type          | Default                                                                  |
| ------------- | ------------------------------------------------------------------------ |
| `NonEmptyStr` | `Mozilla/5.0 (X11; Linux x86_64; rv:153.0) Gecko/20100101 Firefox/153.0` |

The user agent is the signature of your browser. Some sites use it to identify if the request came from a human or a robot.
You can google "what is my user agent" to get yours.

```yaml
network:
  user_agent: Mozilla/5.0 (X11; Linux x86_64; rv:153.0) Gecko/20100101 Firefox/153.0
```

{% hint style="info" %}
If you use flaresolverr, this value **MUST** match with flaresolverr's user agent. Otherwise, flaresolverr cookies won't work
{% endhint %}

{% hint style="info" %}
These crawlers will ignore custom user-agents and will always use `cyberdrop-dl/<version>`

<!-- START_CUSTOM_UA_CRAWLERS -->
- Archive.org
- E621
- MegaNz
- Pawchive
- RealDebrid
- Transfer.it
<!-- END_CUSTOM_UA_CRAWLERS -->

{% endhint %}
