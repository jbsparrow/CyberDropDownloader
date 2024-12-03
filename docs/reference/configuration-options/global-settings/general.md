---
description: These are some general settings that will be used regardless of which config is loaded
---
# General

## `allow_insecure_connections`

| Type           | Default  |
|----------------|----------|
| `bool` | `false`|

Setting this to `true` will allow the program to connect to websites without SSL encryption (insecurely).


{% hint style="danger" %}
This will make the connection insecure, and sensitive data may be exposed. You should only enable this option if you know what you are doing. For your safety, is recommended to always use a secure HTTPS connection to protect your privacy.
{% endhint %}


## `user_agent`

| Type           | Default  |
|----------------|----------|
| `NonEmptyStr` | `Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0`|

The user agent is the signature of your browser, it's how it is represented to websites you connect to. You can google "what is my user agent" to see what yours may be.


{% hint style="info" %}
If you use flaresolverr, this value must match with flaresolverr user agent for its cookies to work
{% endhint %}


## `proxy`

| Type           | Default  |
|----------------|----------|
| `HttpURL` or `null` | `null`|

The proxy you want CDL to use. Only `http` proxies are supported. Ex: `https://user:pass@ip:port`

## `flaresolverr`

| Type           | Default  |
|----------------|----------|
| `HttpURL` or `null` | `null`|

Flaresolverr instance you want CDL to use. Must be a valid `http` URL Ex: `http://ip:port`

## `max_file_name_length`

| Type           | Default  |
|----------------|----------|
| `PositiveInt` | `95`|

This is the maximum number of characters allowable in a filename.

## `max_folder_name_length`

| Type           | Default  |
|----------------|----------|
| `PositiveInt` | `95`|

This is the maximum number of characters allowable in a folder name.

## `required_free_space`

| Type           | Default  |
|----------------|----------|
| `ByteSize` | `5GB`|

This is the minimum amount of free space require to start new downloads.
