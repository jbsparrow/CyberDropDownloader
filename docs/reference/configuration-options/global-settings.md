---
description: These are all of the configuration options for Global Settings.
---

# Global Settings

<details>

<summary>General</summary>

This is some general settings that will be used regardless of which config is loaded.

***

* allow\_insecure\_connections

Setting this to true will allow the program to connect to websites without ssl (insecurely).

***

* user\_agent

The user agent is the signature of your browser, it's how it is represented to websites you connect to. You can google "what is my user agent" to see what yours may be.

**Note:** if you use flaresolverr, this value must match with flaresolverr user agent for its cookies to work.

***

* proxy

The proxy you want CDL to utilize. Ex. `https://user:pass@ip:port`

***

* flaresolverr

The IP for flaresolverr you want CDL to utilize. Ex. `ip:port`

***

* max\_file\_name\_length

This is the maximum number of characters allowable in a filename.

***

* max\_folder\_name\_length

This is the maximum number of characters allowable in a folder name.

***

* required\_free\_space

This is the amount of free space (in gigabytes) that the program will stop initiating downloads at.

</details>

<details>

<summary>Rate Limiting Options</summary>

These are limiting options for the program.

***

* connection\_timeout

The number of seconds to wait while connecting to a website before timing out.

***

* download\_attempts

The number of download attempts per file. Regardless of this value, some conditions (such as a 404 HTTP status) will cause a file to not be retried at all.

***

* read\_timeout

The number of seconds to wait while reading data from a website before timing out. If it's a download, it will be retried and won't count against the download\_attempts limit.

***

* rate\_limit

This is the maximum number of requests that can be made by the program per second.

***

* download\_delay

This is the number of seconds to wait between downloads to the same domain.

Some domains have internal limits set by the program, such as Bunkrr, CyberFile, etc.

***

* max\_simultaneous\_downloads

This is the maximum number of files that can be downloaded simultaneously.

***

* max\_simultaneous\_downloads\_per\_domain

This is the maximum number of files that can be downloaded from a single domain simultaneously.

Some domains have internal limits set by the program, such as Bunkrr, CyberFile, etc.

***

* download\_speed\_limit

This is the max rate of downloading in KB for all downloads combined
Set to 0 or `null` to disable

</details>

<details>

<summary>UI Options</summary>

These are the options for controlling the UI of the program

***

* downloading\_item\_limit

This is the limit on the number of items shown in the UI (while downloading) before they are simply added to the overflow number ("and X other files")

***

* refresh\_rate

This is the refresh rate per second for the UI.

***

* scraping\_item\_limit

This is the limit on the number of items shown in the UI (while scraping) before they are simply added to the overflow number ("and X other links")

***

* vi\_mode

This enables vi/vim keybinds while editing/entering text in CDL.

</details>
