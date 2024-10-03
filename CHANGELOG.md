# CHANGELOG

All notable changes to this project will be documented here. For more details, visit the wiki: https://script-ware.gitbook.io

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [5.6.42] -  2024-10-03

This update introduces the following changes:
1. Filter final URL with `--skip-hosts` and `--only-hosts` arguments

#### Details:

- This allows the user to skip or only download from specific bunkr hosts

## [5.6.41] - 2024-10-01

This update introduces the following changes:
1. Fixes crash when unsupported URLs have no parents
2. Display new changelog if an update is available
3. Updated supported sites in Wiki

#### Details:

- Fixes crash if an unsupported url have no parents
- Always display an updated changelog if a new version has been released on Pypi
- Remove Simpcity from supported websites on Wiki

## [5.6.40] - 2024-10-01

This update introduces the following changes:
1. Fixes empty folder cleanup 

#### Details:
- Fixes incorrent path objects on post-runtime folder cleanup

## [5.6.39] - 2024-09-30

This update introduces the following changes:
1. Adds external CHANGELOG file

#### Details:
- Project changes will documented on https://github.com/jbsparrow/CyberDropDownloader/blob/master/CHANGELOG.md for better tracking
- Built-in viewer will fetch CHANGELOG history on first use

## [5.6.38] - 2024-09-30

This update introduces the following changes:
1. Fix `scrape_items` creation for kemono and coomer links

#### Details:
- Fixes parents tracking for kemono and coomer links


## [5.6.37] - 2024-09-30

This update introduces the following changes:
1. Fixes empty folder cleanup on python 3.11

#### Details:
- Fixes logic by walking the directory tree using os.walk to remain compatibility with python 3.11


## [5.6.36] - 2024-09-30

This update introduces the following changes:
1. Delete empty files after a successful run.
2. Added a feature to save the origin of unsupported URLs

#### Details:
- Empty files (0 bytes) inside download_dir will be deleted alongside empty folders after a successful run
- Each unsupported URL will now be saved alongside the URL of the original item they came from (`Unsupported_URLs.txt`)
- Origin is also saved for password protected links, allowing the user to visit the URL (ex. forum post) and retrieve the password if available


## [5.6.35] - 2024-09-30

This update introduces the following changes:
1. Small fixes for sorting system

#### Details:
- Fixes `scan_dir` selection logic


## [5.6.34] - 2024-09-30

This update introduces the following changes:
1. Added a feature to fix the names of multipart archives.

#### Details:
- Multipart archives will be renamed to have the proper naming format when the `--remove-generated-id-from-filenames` argument is passed.


## [5.6.33] - 2024-09-25

This update introduces the following changes:
1. Fix issues with checking how much free space is available on the disk.
2. Skip clearing the console when running with the `--no-ui` flag.

#### Details:

- Fixed an issue with free space not being properly checked when running with the `--retry-failed` flag.
- Made error output more clear when there is not enough free space to download a file.
- Skip clearing the console when running with the `--no-ui` flag to allow users to see the output of all runs done with `--no-ui`.


## [5.6.32] - 2024-09-22

This update introduces the following changes:
1. Add new URLs categorization feature for the URLs.txt file.

#### Details:

- You can now group links under one download folder by adding a category name above the links in the `URLs.txt` file.
- The category name must be prefixed by three dashes (`---`) and must be on a new line.
- The category name will be used as the folder name for the links that follow it.
- To end a category, add three dashes (`---`) on a new line after the links.
- You can have multiple categories in the URLs.txt file, and the links will be grouped accordingly.


For more details, visit the wiki: https://script-ware.gitbook.io/cyberdrop-dl/reference/configuration-options/settings#sorting


## [5.6.30] - 2024-09-21

**SIMPCITY HAS BEEN REMOVED FROM THE SUPPORTED WEBSITES LIST.**

**TO SEE WHY, VISIT THE WIKI:** https://script-ware.gitbook.io/cyberdrop-dl/simpcity-support-dropped

## [5.6.20] - 2024-09-19

This update introduces the following changes:
1. Ability to scrape URLs from PixelDrain text post

#### Details:

- Cyberdrop-DL will now scrape URLs from PixelDrain text posts and make a folder for all the URLs within the post, reducing clutter.


## [5.6.13] - 2024-09-19

This update introduces the following changes:
1. Per-config authentication settings

#### Details:

- If an `authentication.yaml` file is placed within your config directory, it will be used instead of the global authentication values.


## [5.6.12] - 2024-09-19

This update introduces the following changes:
1. Reformat code and organize imports

#### Details:

- Reformatted code to be more readable and removed unused imports.


## [5.6.11] - 2024-09-16

This update introduces the following changes:
1. Detect and raise an error for private gofile folders

#### Details:

- Private gofile folders will now raise an error when attempting to download them instead of crashing CDL


## [5.6.1] - 2024-09-13

This update introduces the following changes:
1. Fixes issue with `--sort-all-downloads`
2. Improves sort status visibility

#### Details:

- The sort status is now display under hash, along with other statuses
- `--sort-all-downloads` is disabled by default, thus only cdl downloads are sorted without the flag
- `sort_folder` can not be the same as the `scan_dir`


## [5.6.0] - 2024-09-13

This update introduces the following changes:
1. Updated the sorting progress UI to display more information.
2. Removed unused functions from progress bars.

#### Details:

- The sorting UI now displays the progress of each folder as it is being processed, including the number of files that have been sorted and the percentage of the folder that has been processed.
- The sorting UI now also shows what folders are in the queue to be sorted.


## [5.5.1] - 2024-09-12

This update introduces the following changes:
1. Small fixes for sorting system

#### Details:

- use `-` instead of `_` for new arguments
- fix bug where `purge_dir` is called for each file, instead of each directory when done


## [5.5.0] - 2024-09-12

This update introduces the following changes:
1. Finalizes new sorting feature
2. add scanning directory for sorting
3. adds progress bar for sorting

#### Details:

- skips need to scan db if `sort_cdl_only` is false
- progress bar for current progress of sorting files, incremented for each folder
- allow for setting a different folder to scan that is independent of the download folder