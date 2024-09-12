"""
C\bCH\bHA\bAN\bNG\bGE\bEL\bLO\bOG\bG
\tVersion 5.4.70


D\bDE\bES\bSC\bCR\bRI\bIP\bPT\bTI\bIO\bON\bN
\tThis update introduces the following changes:
\t\t1. Bug fixes for the `sort_cdl_only` config option.
\t\t2. Introducing logging for sorting operations.

\tDetails:
\t\t- Changed the `--sort-cdl-only` CLI argument to `--sort-all-downloads`.
\t\t- Added logging for sorting operations.
\t\t- Fix improper path handling of the `sort_cdl_only` config option.

\tFor more details, visit the wiki: https://script-ware.gitbook.io


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



C\bCH\bHA\bAN\bNG\bGE\bEL\bLO\bOG\bG
\tVersion 5.5.1

D\bDE\bES\bSC\bCR\bRI\bIP\bPT\bTI\bIO\bON\bN
\tThis update introduces the following changes:
\t\t1. small fixes for sorting system



\tDetails:
\t\t- use - instead of _ for new arguments
\t\t- fix bug where purge_dir is called for each file, instead of each directory when done

"""
