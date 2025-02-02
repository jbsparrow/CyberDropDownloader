# Browser Cookies

Cyberdrop-DL can extract cookies from your browser. These can be used for websites that require login or to pass DDoS-Guard challenges. Only cookies from supported websites are extracted

{% hint style="warning" %}
The `user-agent` config value **MUST** match the `user-agent` of the browser from which you imported the cookies. If they do not match, the cookies will not work
{% endhint %}

## `auto_import`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

Toggles automatic import of cookies at the start of each run

## `browsers`

| Type             | Default    |
| ---------------- | ---------- |
| `list[BROWSERS]` | `[chrome]` |

List of browsers to use for extraction. Each item must be a supported browser's name, separated by commas

### Supported Browsers

| Browser   | Windows            | Linux              | MacOS              |
| --------- | ------------------ | ------------------ | ------------------ |
| Arc       | :x:                | :x:                | :white_check_mark: |
| Brave     | :x:                | :white_check_mark: | :white_check_mark: |
| Chrome    | :x:                | :white_check_mark: | :white_check_mark: |
| Chromium  | :x:                | :white_check_mark: | :white_check_mark: |
| Edge      | :x:                | :white_check_mark: | :white_check_mark: |
| Firefox   | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| LibreWolf | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| Lynx      | :x:                | :white_check_mark: | :x:                |
| Opera     | :x:                | :white_check_mark: | :white_check_mark: |
| Opera_GX  | :x:                | :x:                | :white_check_mark: |
| Safari    | :x:                | :x:                | :white_check_mark: |
| Vivaldi   | :x:                | :white_check_mark: | :white_check_mark: |
| W3M       | :x:                | :white_check_mark: | :x:                |

{% hint style="info" %}
If cookies exists on multiple selected browsers, the cookies from the last browser in the list will have priority
{% endhint %}

{% hint style="info" %}
If the value entered is `null` or an empty list, no cookies will be extracted from any browser
{% endhint %}

## `sites`

| Type            | Default         |
| --------------- | --------------- |
| `list[DOMAINS]` | `[<ALL_SITES>]` |

List of domains to extract cookies from. You can put any domain on the list, but only sites supported by Cyberdrop-DL will be taken into account

## Manual Cookie Extraction

If cookie extraction fails, you can manually extract the cookies from your browser using tools like [cookie-editor](https://cookie-editor.com) and save them at `AppData/Cookies/<site_name>.txt`. The file must be a Netscape formatted cookie file. You can use any name for the file as long as it has a `.txt` extension.

{% hint style="info" %}
Multiple cookie files are supported. You could have a `SocialMediaGirls.txt` file and a `cyberdrop.txt` file, for example
{% endhint %}
