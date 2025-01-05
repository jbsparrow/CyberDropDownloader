from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.clients.errors import CDLBaseError

if TYPE_CHECKING:
    from requests import Response

ERROR_CODES = {
    -1: "Internal error",
    1: "Missing parameter",
    2: "Bad parameter value",
    3: "Unknown method",
    4: "Method not allowed",
    5: "Slow down",
    6: "Ressource unreachable",
    7: "Resource not found",
    8: "Bad token",
    9: "Permission denied",
    10: "Two-Factor authentication needed",
    11: "Two-Factor authentication pending",
    12: "Invalid login",
    13: "Invalid password",
    14: "Account locked",
    15: "Account not activated",
    16: "Unsupported hoster",
    17: "Hoster in maintenance",
    18: "Hoster limit reached",
    19: "Hoster temporarily unavailable",
    20: "Hoster not available for free users",
    21: "Too many active downloads",
    22: "IP Address not allowed",
    23: "Traffic exhausted",
    24: "File unavailable",
    25: "Service unavailable",
    26: "Upload too big",
    27: "Upload error",
    28: "File not allowed",
    29: "Torrent too big",
    30: "Torrent file invalid",
    31: "Action already done",
    32: "Image resolution error",
    33: "Torrent already active",
    34: "Too many requests",
    35: "Infringing file",
    36: "Fair Usage Limit",
}


class RealDebridError(CDLBaseError):
    """Base RealDebrid API error."""

    def __init__(self, response: Response) -> None:
        url = URL(response.url)
        self.path = url.path
        try:
            JSONResp: dict = response.json()
            code = JSONResp.get("error_code")
            if code == 16:
                code = 7
            error = ERROR_CODES.get(code, "Unknown error")

        except AttributeError:
            code = response.status_code
            error = f"{code} - {HTTPStatus(code).phrase}"

        error = error.capitalize()

        """This error will be thrown when a scrape fails."""
        ui_message = f"{code} RealDebrid Error"
        super().__init__(ui_message, message=error, status=code, origin=url)
