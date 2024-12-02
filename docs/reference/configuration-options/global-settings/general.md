---
description: These are some general settings that will be used regardless of which config is loaded
---
# General

## `allow_insecure_connections`

Setting this to true will allow the program to connect to websites without SSL (insecurely).

## `user_agent`

The user agent is the signature of your browser, it's how it is represented to websites you connect to. You can google "what is my user agent" to see what yours may be.


{% hint style="info" %}
**NOTE:** if you use flaresolverr, this value must match with flaresolverr user agent for its cookies to work
{% endhint %}


## `proxy`

The proxy you want CDL to utilize. Ex. `https://user:pass@ip:port`

## `flaresolverr`

Flaresolverr instance you want CDL to use. Must be a valid httpURL Ex: `http://ip:port`

## `max_file_name_length`

This is the maximum number of characters allowable in a filename.

## `max_folder_name_length`

This is the maximum number of characters allowable in a folder name.

## `required_free_space`

This is the amount of free space (in gigabytes) that the program will stop initiating downloads at.
