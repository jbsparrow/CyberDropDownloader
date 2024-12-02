# Browser Cookies

Cyberdrop-DL can extract cookies from your browser. These can be used for websites that require login or to pass DDoS-Guard challenges. Only cookies from supported websites are extracted

## `auto_import`

toggles automatic import of cookies at the start of each run

## `browsers`

| Type           | Default  |
|----------------|----------|
| list[BROWSERS] | [chrome] |


List a browser to use for extraction. List must be the browser name, with one of more of the values from the table below, separated by commas

### Supported browsers

| Browser   | Windows            | Linux              | MacOS              |
|-----------|--------------------|--------------------|--------------------|
| Brave     | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| Chrome    | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| Chromium  | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| Edge      | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| Firefox   | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| LibreWolf | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| Opera     | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| Opera_GX  | :white_check_mark: | :x:                | :white_check_mark: |
| Safari    | :x:                | :x:                | :white_check_mark: |
| Vivaldi   | :white_check_mark: | :white_check_mark: | :white_check_mark: |


{% hint style="info" %}
**NOTE:** If cookies exists on multiple selected browsers, the cookies from the last browser in the list will have priority
{% endhint %}

{% hint style="info" %}
**NOTE:**  If the value entered is `null` or an empty list, no cookies will be extracted from any browser
{% endhint %}

## `sites`

| Type           | Default  |
|----------------|----------|
| list[DOMAINS] | [<ALL_SITES>] |

List of domains to extract cookies from. Only sites supported by Cyberdrop-DL will be taken into account

{% hint style="info" %}
**NOTE:**  If the value entered is `null` or an empty list, cookies will be extract from all supported sites
{% endhint %}

## Manual Cookie Extraction

If cookie extraction fails, you can manually extract the cookies from your browser and save them at `AppData/Cookies/<domain>.txt`, where domain is the domain of the site you exported the cookies from. The file must be a Netscape formatted cookie file
