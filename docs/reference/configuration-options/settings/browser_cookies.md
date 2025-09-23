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

## `browser`

| Type             | Default    |
| ---------------- | ---------- |
| `BROWSER` | `firefox` |

A browser to use for extraction. Browser must be a supported browser's name.

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

## `sites`

| Type            | Default         |
| --------------- | --------------- |
| `list[DOMAINS]` | `[<<ALL_SUPPORTED_SITES>>]` |

List of domains to extract cookies from. You can put any domain on the list, even if they are not officially supported.

## Manual Cookie Extraction

If cookie extraction fails, you can manually extract the cookies from your browser using tools like [cookie-editor](https://cookie-editor.com) and save them at `AppData/Cookies/<site_name>.txt`. The file must be a Netscape formatted cookie file. You can use any name for the file as long as it has a `.txt` extension.

See: [How to extract cookies (DDoSGuard or login errors) #839](https://github.com/jbsparrow/CyberDropDownloader/discussions/839) for detailed instructions

{% hint style="info" %}
Multiple cookie files are supported. You could have a `SocialMediaGirls.txt` file and a `cyberdrop.txt` file, for example
{% endhint %}
