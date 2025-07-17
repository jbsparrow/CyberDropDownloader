from __future__ import annotations

from typing import TYPE_CHECKING, Any

from requests import Session
from requests.exceptions import RequestException

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import RealDebridError
from cyberdrop_dl.managers.real_debrid.errors import ERROR_CODES

if TYPE_CHECKING:
    from requests import Response

RATE_LIMIT = 250


class RealDebridApi:
    """Real-Debrid API Implementation. All methods return their JSON response (if any).

    For details, visit: https://api.real-debrid.com

    Unless specified otherwise, all API methods require authentication.

    The API is limited to 250 requests per minute. Use `rate_limiter` context manager to auto limit the requests being made

    Dates are formatted according to the Javascript method `date.toJSON`.
    Use `convert_special_types` to convert response values to `datetime.date`, `datetime.datetime`, `datetime.timedelta` and `yarl.URL` when applicable

    """

    API_ENTRYPOINT = AbsoluteHttpURL("https://api.real-debrid.com/rest/1.0")

    def __init__(self, api_token: str | None = None) -> None:
        self._session = Session()
        self.unrestrict = Unrestrict(self)
        self.hosts = Hosts(self)
        self.update_token(api_token or "")

    def _get(self, path: str, *, entrypoint: AbsoluteHttpURL = API_ENTRYPOINT, **query_params) -> Any:
        response = self._session.get(url=str(entrypoint / path), params=query_params)
        return self.handle_response(response)

    def _post(self, path: str, *, entrypoint: AbsoluteHttpURL = API_ENTRYPOINT, **data) -> Any:
        response = self._session.post(str(entrypoint / path), data=data)
        return self.handle_response(response)

    def update_token(self, new_token: str) -> None:
        self._api_token = new_token
        self._session.headers.update({"Authorization": f"Bearer {self._api_token}"})

    @staticmethod
    def handle_response(response: Response) -> Any:
        try:
            json_resp: dict[str, Any] = response.json()
            response.raise_for_status()
        except RequestException:
            code = json_resp.get("error_code")
            if not code or code not in ERROR_CODES:
                raise
            code = 7 if code == 16 else code
            msg = ERROR_CODES.get(code, "Unknown error")
            raise RealDebridError(response, code, msg) from None
        except AttributeError:
            response.raise_for_status()
            return response.text
        else:
            return json_resp


class Unrestrict:
    def __init__(self, api: RealDebridApi) -> None:
        self.api = api

    def check(self, link: AbsoluteHttpURL, password: str | None = None) -> dict:
        """Check if a file is downloadable on the concerned hoster. This request does not require authentication."""
        return self.api._post("unrestrict/check", link=link, password=password)

    def link(self, link: AbsoluteHttpURL, password: str | None = None, remote: bool = False) -> AbsoluteHttpURL:
        """Unrestrict a hoster link and get a new unrestricted link."""
        json_resp: dict = self.api._post("unrestrict/link", link=link, password=password, remote=remote)
        return AbsoluteHttpURL(json_resp["download"])

    def folder(self, link: AbsoluteHttpURL) -> list[AbsoluteHttpURL]:
        """Unrestrict a hoster folder link and get individual links, returns an empty array if no links found."""
        links: list = self.api._post("unrestrict/folder", link=link)
        return [AbsoluteHttpURL(link) for link in links]


class Hosts:
    def __init__(self, api: RealDebridApi) -> None:
        self.api = api

    def get(self) -> list:
        """Get supported hosts. This request does not require authentication."""
        return self.api._get("hosts")

    def regex(self) -> list:
        """Get all supported links Regex, useful to find supported links inside a document. This request does not require authentication."""
        return self.api._get("hosts/regex")

    def regex_folder(self) -> list:
        """Get all supported folder Regex, useful to find supported links inside a document. This request does not require authentication."""
        return self.api._get("hosts/regexFolder")

    def domains(self) -> list:
        """Get all hoster domains supported on the service. This request does not require authentication."""
        return self.api._get("hosts/domains")
