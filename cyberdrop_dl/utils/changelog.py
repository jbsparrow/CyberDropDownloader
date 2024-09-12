"""
C\bCH\bHA\bAN\bNG\bGE\bEL\bLO\bOG\bG
\tVersion 5.4.61 - 5.4.68


D\bDE\bES\bSC\bCR\bRI\bIP\bPT\bTI\bIO\bON\bN
\tThis update introduces the following changes:
\t\t1. Added a configuration option `sort_cdl_only` to enable sorting based on download history.
\t\t2. Implemented asynchronous iteration for fetching unique download paths from the history.
\t\t3. Updated the sorting logic to conditionally use either the download directory or the history based on the configuration.
\t\t4. Improved error handling and logging for better debugging and maintenance.
\t\t5. Added automatic debugging support for vscode.
\t\t6. Added a new option to view the changelog.

\tDetails:
\t\t- The `sort_cdl_only` option allows users to choose whether to sort files based on the download history or the current download directory.
\t\t- Asynchronous iteration ensures efficient handling of large datasets when fetching unique download paths.
\t\t- Conditional sorting logic provides flexibility and enhances the user experience by allowing customized sorting behavior.
\t\t- Debug mode is automatically enabled in vscode for easier debugging and troubleshooting.
\t\t- The changelog option provides users with a quick overview of the latest changes and updates.

\tFor more details, visit the wiki: https://script-ware.gitbook.io
"""
