"""

------------------------------------------------------------

C\bCH\bHA\bAN\bNG\bGE\bEL\bLO\bOG\bG
\tVersion 5.7.0


D\bDE\bES\bSC\bCR\bRI\bIP\bPT\bTI\bIO\bON\bN
\tThis update introduces the following changes:
\t\t1. Added a caching system to prevent re-scraping of URLs.

\tDetails:
\t\t- Cyberdrop-DL will now cache responses from websites in order to prevent re-scraping.
\t\t- The last page of a thread will not be cached in order to ensure that new content is properly fetched.
\t\t- Forums will be cached for 30 days while file hosts will be cached for 7 days.


\tFor more details, visit the wiki: https://script-ware.gitbook.io

------------------------------------------------------------

C\bCH\bHA\bAN\bNG\bGE\bEL\bLO\bOG\bG
\tVersion 5.6.34


D\bDE\bES\bSC\bCR\bRI\bIP\bPT\bTI\bIO\bON\bN
\tThis update introduces the following changes:
\t\t1. Added a feature to fix the names of multipart archives.

\tDetails:
\t\t- Multipart archives will be renamed to have the proper naming format when the --remove-generated-id-from-filenames argument is passed.


\tFor more details, visit the wiki: https://script-ware.gitbook.io

------------------------------------------------------------

C\bCH\bHA\bAN\bNG\bGE\bEL\bLO\bOG\bG
\tVersion 5.6.33


D\bDE\bES\bSC\bCR\bRI\bIP\bPT\bTI\bIO\bON\bN
\tThis update introduces the following changes:
\t\t1. Fix issues with checking how much free space is available on the disk.
\t\t2. Skip clearing the console when running with the --no-ui flag.

\tDetails:
\t\t- Fixed an issue with free space not being properly checked when running with the --retry-failed flag.
\t\t- Made error output more clear when there is not enough free space to download a file.
\t\t- Skip clearing the console when running with the --no-ui flag to allow users to see the output of all runs done with --no-ui.


\tFor more details, visit the wiki: https://script-ware.gitbook.io

------------------------------------------------------------

C\bCH\bHA\bAN\bNG\bGE\bEL\bLO\bOG\bG
\tVersion 5.6.32


D\bDE\bES\bSC\bCR\bRI\bIP\bPT\bTI\bIO\bON\bN
\tThis update introduces the following changes:
\t\t1. Add new URLs categorization feature for the URLs.txt file.

\tDetails:
\t\t- You can now group links under one download folder by adding a category name above the links in the URLs.txt file.
\t\t- The category name must be prefixed by three dashes (---) and must be on a new line.
\t\t- The category name will be used as the folder name for the links that follow it.
\t\t- To end a category, add three dashes (---) on a new line after the links.
\t\t- You can have multiple categories in the URLs.txt file, and the links will be grouped accordingly.


\tFor more details, visit the wiki: https://script-ware.gitbook.io/cyberdrop-dl/reference/configuration-options/settings#sorting

------------------------------------------------------------

C\bCH\bHA\bAN\bNG\bGE\bEL\bLO\bOG\bG
\tVersion 5.6.30


S\bSI\bIM\bMP\bPC\bCI\bIT\bTY\bY H\bHA\bAS\bS B\bBE\bEE\bEN\bN R\bRE\bEM\bMO\bOV\bVE\bED\bD F\bFR\bRO\bOM\bM T\bTH\bHE\bE S\bSU\bUP\bPP\bPO\bOR\bRT\bTE\bED\bD W\bWE\bEB\bBS\bSI\bIT\bTE\bES\bS L\bLI\bIS\bST\bT.\b.

T\bTO\bO S\bSE\bEE\bE W\bWH\bHY\bY,\b, V\bVI\bIS\bSI\bIT\bT T\bTH\bHE\bE W\bWI\bIK\bKI\bI:\b: https://script-ware.gitbook.io/cyberdrop-dl/simpcity-support-dropped

------------------------------------------------------------

C\bCH\bHA\bAN\bNG\bGE\bEL\bLO\bOG\bG
\tVersion 5.6.20


D\bDE\bES\bSC\bCR\bRI\bIP\bPT\bTI\bIO\bON\bN
\tThis update introduces the following changes:
\t\t1. Ability to scrape URLs from PixelDrain text post

\tDetails:
\t\t- Cyberdrop-DL will now scrape URLs from PixelDrain text posts and make a folder for all the URLs within the post, reducing clutter.


\tFor more details, visit the wiki: https://script-ware.gitbook.io

------------------------------------------------------------

C\bCH\bHA\bAN\bNG\bGE\bEL\bLO\bOG\bG
\tVersion 5.6.13


D\bDE\bES\bSC\bCR\bRI\bIP\bPT\bTI\bIO\bON\bN
\tThis update introduces the following changes:
\t\t1. Per-config authentication settings

\tDetails:
\t\t- If an authentication.yaml file is placed within your config directory, it will be used instead of the global authentication values.


\tFor more details, visit the wiki: https://script-ware.gitbook.io

------------------------------------------------------------

C\bCH\bHA\bAN\bNG\bGE\bEL\bLO\bOG\bG
\tVersion 5.6.12


D\bDE\bES\bSC\bCR\bRI\bIP\bPT\bTI\bIO\bON\bN
\tThis update introduces the following changes:
\t\t1. Reformat code and organize imports

\tDetails:
\t\t- Reformatted code to be more readable and removed unused imports.


\tFor more details, visit the wiki: https://script-ware.gitbook.io

------------------------------------------------------------

C\bCH\bHA\bAN\bNG\bGE\bEL\bLO\bOG\bG
\tVersion 5.6.11


D\bDE\bES\bSC\bCR\bRI\bIP\bPT\bTI\bIO\bON\bN
\tThis update introduces the following changes:
\t\t1. Detect and raise an error for private gofile folders

\tDetails:
\t\t- Private gofile folders will now raise an error when attempting to download them instead of crashing CDL


\tFor more details, visit the wiki: https://script-ware.gitbook.io

------------------------------------------------------------

C\bCH\bHA\bAN\bNG\bGE\bEL\bLO\bOG\bG
\tVersion 5.6.1


D\bDE\bES\bSC\bCR\bRI\bIP\bPT\bTI\bIO\bON\bN
\tThis update introduces the following changes:
\t\t1. Fixes issue with --sort-all-downloads
\t\t2. Improves sort status visibility

\tDetails:
\t\t- The sort status is now display under hash, along with other statuses
\t\t- --sort-all-downloads is disabled by default, thus only cdl downloads are sorted without the flag
\t\t- The sort_folder can not be the same as the scan_dir


\tFor more details, visit the wiki: https://script-ware.gitbook.io

------------------------------------------------------------

C\bCH\bHA\bAN\bNG\bGE\bEL\bLO\bOG\bG
\tVersion 5.6.0


D\bDE\bES\bSC\bCR\bRI\bIP\bPT\bTI\bIO\bON\bN
\tThis update introduces the following changes:
\t\t1. Updated the sorting progress UI to display more information.
\t\t2. Removed unused functions from progress bars.

\tDetails:
\t\t- The sorting UI now displays the progress of each folder as it is being processed, including the number of files that have been sorted and the percentage of the folder that has been processed.
\t\t- The sorting UI now also shows what folders are in the queue to be sorted.


\tFor more details, visit the wiki: https://script-ware.gitbook.io

------------------------------------------------------------

C\bCH\bHA\bAN\bNG\bGE\bEL\bLO\bOG\bG
\tVersion 5.5.1

D\bDE\bES\bSC\bCR\bRI\bIP\bPT\bTI\bIO\bON\bN
\tThis update introduces the following changes:
\t\t1. small fixes for sorting system



\tDetails:
\t\t- use - instead of _ for new arguments
\t\t- fix bug where purge_dir is called for each file, instead of each directory when done


\tFor more details, visit the wiki: https://script-ware.gitbook.io

------------------------------------------------------------

C\bCH\bHA\bAN\bNG\bGE\bEL\bLO\bOG\bG
\tVersion 5.5.0

D\bDE\bES\bSC\bCR\bRI\bIP\bPT\bTI\bIO\bON\bN
\tThis update introduces the following changes:
\t\t1. Finalizes new sorting feature
\t\t2. add scanning directory for sorting
\t\t3. adds progress bar for sorting



\tDetails:
\t\t- skips need to scan db if sort_cdl_only is false
\t\t- progress bar for current progress of sorting files,incremented for each folder
\t\t- allow for setting a different folder to scan that is independent of the download folder

\tFor more details, visit the wiki: https://script-ware.gitbook.io

------------------------------------------------------------

"""
