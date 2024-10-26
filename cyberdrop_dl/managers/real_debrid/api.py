from requests import Session
from pathlib import Path
from yarl import URL
from requests.exceptions import RequestException
from cyberdrop_dl.managers.real_debrid.errors import RealDebridError
from datetime import date, datetime, timedelta
import time
from contextlib import contextmanager

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from requests import Response

MAGNET_PREFIX = 'magnet:?xt=urn:btih:'
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DATE_ISO_FORMAT = "%Y-%m-%dT%H:%M:%S%z"
DATE_JSON_FORMAT =  "%Y-%m-%dT%H:%M:%S.%fZ"
RATE_LIMIT = 250 # per minute

class RealDebridApi:
    """
    Real-Debrid API Implementation. All methods return their JSON response (if any)
    
    For details, visit: https://api.real-debrid.com
    
    Unless specified otherwise, all API methods require authentication.

    The API is limited to 250 requests per minute. Use `rate_limiter` context manager to auto limit the requests being made

    Dates are formatted according to the Javascript method `date.toJSON`. 
    Use `convert_special_types` to convert response values to `datetime.date`, `datetime.datetime`, `datetime.timedelta` and `yarl.URL` when applicable

    """
    API_ENTRYPOINT = URL('https://api.real-debrid.com/rest/1.0')
    API_OAUTH_ENTRYPOINT = URL("https://api.real-debrid.com/oauth/v2/")

    def __init__(self, api_token: Optional[str] = None, convert_special_types: bool= False):
        self._session = Session()
        self._last_request_time = 0
        self._convert_special_types = convert_special_types
        self.auth = OAuth(self)
        self.system = System(self)
        self.user = User(self)
        self.unrestrict = Unrestrict(self)
        self.traffic = Traffic(self)
        self.streaming = Streaming(self)
        self.downloads = Downloads(self)
        self.torrents = Torrents(self)
        self.hosts = Hosts(self)
        self.settings = Settings(self)
        self.update_token(api_token)
       
    def get(self, path: str, *, entrypoint: URL = API_ENTRYPOINT, **query_params):
        response = self._session.get(url = entrypoint / path, params= query_params)
        return self.handle_response(response)

    def post(self, path: str, *, entrypoint: URL = API_ENTRYPOINT, **data):
        response = self._session.post(entrypoint / path, data=data)
        return self.handle_response(response)
    
    def put(self, path:str, filepath: Path, *,  entrypoint: URL = API_ENTRYPOINT, **query_params):
        with open(filepath, 'rb') as file:
            response = self._session.put(entrypoint/ path, data=file, params=query_params)
        return self.handle_response(response, path)

    def delete(self, path: str, *, entrypoint: URL = API_ENTRYPOINT):
        request = self._session.delete(entrypoint / path)
        return self.handle_response(request)
            
    def update_token(self, new_token: str) -> None:
        self._api_token = new_token
        self._session.headers.update({'Authorization': f"Bearer {self._api_token}"})

    def handle_response(self, response: 'Response') -> dict | str | None:
        try:
            response.raise_for_status()
            JSONResp: dict = response.json()
            return JSONResp
        except RequestException:
            raise RealDebridError(response)    
        except AttributeError:
            return response.text
    
    @contextmanager
    def rate_limiter(self, buffer: float = 0.2):
        """Context manager to rate limit API requests
        
        Buffer is % of RATE_LIMIT"""
        actual_rate_limit = RATE_LIMIT * ( 1 - buffer)
        elapsed = time.time() - self._last_request_time
        wait_time = max(0, (1 / actual_rate_limit ) - elapsed)
        time.sleep(wait_time)  
        self._last_request_time = time.time() 
        yield  
    

class OAuth:
    '''RealDebrid authentication via OAuth API'''

    def __init__(self, api: RealDebridApi):
        self.api = api
        self.grant_type = 'http://oauth.net/grant_type/device/1.0'

    def get_devide_code(self,  client_id: str, new_credentials:bool=False) -> dict:
        """Get authentication data"""
        JSONResp = self.api.get('device/code', entrypoint=self.api.API_OAUTH_ENTRYPOINT, client_id= client_id, new_credentials=new_credentials)
        if self.api._convert_special_types:
            JSONResp['expires_in'] = timedelta(seconds=JSONResp['expires_in'])
            JSONResp['verification_url'] = URL(JSONResp['verification_url'])
        return JSONResp

    def get_credentials(self, client_id: str, device_code: str):
        """Verify authentication data and get credentials"""
        return self.api.get('device/credentials', entrypoint=self.api.API_OAUTH_ENTRYPOINT, client_id = client_id, code=device_code)
    
    def get_token(self, client_id: str, client_secret: str, device_code: str):
        """Get token from credentials"""
        JSONResp = self.api.post('token', entrypoint=self.api.API_OAUTH_ENTRYPOINT, client_id= client_id, client_secret=client_secret, code=device_code, grant_type = self.grant_type)
        if self.api._convert_special_types:
            JSONResp['expires_in'] = timedelta(seconds=JSONResp['expires_in'])
        self.api.update_token(JSONResp['access_token'])
        return JSONResp
        
    def get_new_token(self, client_id: str, client_secret: str, refresh_token: str):
        """Get a new token"""
        return self.get_token(client_id= client_id, client_secret=client_secret, device_code=refresh_token)
    
    def refresh_token(self, client_id: str, client_secret: str, refresh_token: str):
        """Calls `get_new_token`"""
        return self.get_new_token(client_id= client_id, client_secret=client_secret, refresh_token=refresh_token)

class System:
    def __init__(self, api: RealDebridApi):
        self.api = api

    def disable_token(self) -> None:
        '''Disable current access token, returns 204 HTTP code'''
        return self.api.get('disable_access_token')

    def time(self):
        '''Get server time. This request does not require authentication'''
        date_str = self.api.get('time')
        if self.api._convert_special_types:
            return datetime.strptime(date_str, DATE_FORMAT)
        return date_str
        
    def iso_time(self):
        '''Get server time as ISO (with timezone). This request does not require authentication'''
        date_str = self.api.get('time/iso')
        if self.api._convert_special_types:
            return datetime.strptime(date_str, DATE_ISO_FORMAT)
        return date_str

class User:
    def __init__(self, api: RealDebridApi):
        self.api = api

    def get(self) -> dict:
        '''Returns information about the current user'''
        JSONResp = self.api.get('user')
        if self.api._convert_special_types:
            JSONResp['avatar'] = URL(JSONResp['avatar'])
            JSONResp['premium'] = timedelta(seconds=JSONResp['avatar'])
            JSONResp['avatar'] = URL(JSONResp['avatar'])
            JSONResp['expiration']  = datetime.strptime(JSONResp['expiration'], "%Y-%m-%dT%H:%M:%S.%fZ")
        return JSONResp

class Unrestrict:
    def __init__(self, api: RealDebridApi):
        self.api = api

    def check(self, link: URL, password: Optional[str] =None):
        """Check if a file is downloadable on the concerned hoster. This request does not require authentication"""
        return self.api.post('unrestrict/check', link=link, password=password)

    def link(self, link: URL, password: Optional[str] = None, remote: bool=False) -> dict:
        """Unrestrict a hoster link and get a new unrestricted link"""
        JSONResp = self.api.post('unrestrict/link', link=link, password=password, remote=remote)
        if self.api._convert_special_types:
            JSONResp['download'] = URL(JSONResp['download'] )
        return JSONResp
    
    def folder(self, link: URL) -> list:
        """Unrestrict a hoster folder link and get individual links, returns an empty array if no links found"""
        links = self.api.post('unrestrict/folder', link=link)
        if self.api._convert_special_types:
            links = [URL(link) for link in links]
        return links
    
    def container_file(self, filepath: Path) -> dict:
        """Decrypt a container file (RSDF, CCF, CCF3, DLC)"""
        return self.api.put('unrestrict/containerFile', filepath=filepath)

    def container_link(self, link: URL) -> dict:
        """Decrypt a container file from a link"""
        return self.api.post('unrestrict/containerLink', link=link)
    
class Traffic:
    def __init__(self, api: RealDebridApi):
        self.api = api

    def get(self):
        """Get traffic informations for limited hosters (limits, current usage, extra packages)"""
        return self.api.get('traffic')

    def details(self, start: date = None, end: date=None):
        """Get traffic details on each hoster used during a defined period"""
        JSONResp = self.api.get('traffic/details', start=start, end=end) 
        if self.api._convert_special_types:
            JSONResp = {datetime.strptime(key, "%Y-%m-%d").date(): value
            for key, value in JSONResp.items()}   
        return JSONResp
    
class Streaming:
    def __init__(self, api: RealDebridApi):
        self.api = api

    def transcode(self, id: str):
        """Get transcoding links for given file, {id} from /downloads or /unrestrict/link"""
        return self.api.get(f"/streaming/transcode/{id}")

    def media_info(self, id: str):
        """Get detailed media information for the given file id, {id} from /downloads or /unrestrict/link"""
        return self.api.get(f"/streaming/mediaInfos/{id}")
    
class Downloads:
    def __init__(self, api: RealDebridApi):
        self.api = api

    def get(self, offset: int =None, page: int=None, limit:int=None ):
        """Get user downloads list"""
        JSONResp = self.api.get('downloads', offset=offset, page=page, limit=limit)
        if self.api._convert_special_types:
            for download in JSONResp:
                download['generated'] = datetime.strptime(download['generated'], DATE_JSON_FORMAT)
        return JSONResp

    def delete(self, id: str):
        """Delete a link from downloads list, returns 204 HTTP code"""
        return self.api.delete(f'/downloads/delete/{id}')

class Torrents:
    def __init__(self, api: RealDebridApi):
        self.api = api
        self.POSIBLE_STATUS = ['magnet_error', 'magnet_conversion', 'waiting_files_selection', 'queued', 'downloading', 'downloaded', 'error', 'virus', 'compressing', 'uploading', 'dead']

    def get(self, offset:int=None, page:int=None, limit:int=None, filter: str=None ):
        """Get user torrents list"""
        JSONResp: list[dict] = self.api.get('torrents', offset=offset, page=page, limit=limit, filter=filter)
        if self.api._convert_special_types:
            for torrent in JSONResp:
                torrent['added'] = datetime.strptime(torrent['added'], DATE_JSON_FORMAT)
                if torrent.get('ended'):
                    torrent['ended'] = datetime.strptime(torrent['ended'], DATE_JSON_FORMAT)
            
        return JSONResp

    def info(self, id:str):
        """Get all informations on the asked torrent"""
        JSONResp: list[dict] = self.api.get(f'/torrents/info/{id}')
        if self.api._convert_special_types:
            for torrent in JSONResp:
                torrent['added'] = datetime.strptime(torrent['added'], DATE_JSON_FORMAT)
                if torrent.get('ended'):
                    torrent['ended'] = datetime.strptime(torrent['ended'], DATE_JSON_FORMAT)
            
        return JSONResp

    def instant_availability(self, *hash: str):
        """
        Get list of instantly available file IDs by hoster, {hash} is the SHA1 of the torrent.
        You can test multiple hashes adding multiple /{hash} at the end of the request"""
        return self.api.get('torrents/instantAvailability/' + "/".join(*hash))

    def active_count(self):
        """Get currently active torrents number and the current maximum limit"""
        return self.api.get('torrents/activeCount')
    
    def available_hosts(self):
        """Get available hosts to upload the torrent to"""
        return self.api.get('torrents/availableHosts')

    def add_file(self, filepath:Path, host:Optional[str]=None):
        """Add a torrent file to download, return a 201 HTTP code"""
        return self.api.put('torrents/addTorrent', filepath=filepath, host=host)
    
    def add_magnet(self, magnet:str, host:Optional[str]=None):
        """Add a magnet link to download, returns a 201 HTTP code"""
        if MAGNET_PREFIX not in magnet:
            magnet = f"{MAGNET_PREFIX}{magnet}"
        return self.api.post('torrents/addMagnet', magnet=magnet, host=host)
    
    def select_files(self, id:str, *files:str):
        """Select files of a torrent to start it, returns 204 HTTP code
        
        files =	Selected files IDs (comma separated) or 'all'"""
        return self.api.post(f'/torrents/selectFiles/{id}', files=','.join(files))
    
    def delete(self, id:str):
        """Delete a torrent from torrents list, returns 204 HTTP code"""
        return self.api.delete(f'/torrents/delete/{id}')

class Hosts:
    def __init__(self, api:RealDebridApi):
        self.api = api

    def get(self):
        """Get supported hosts. This request does not require authentication"""
        return self.api.get('hosts')        
    
    def status(self):
        """Get status of supported hosters or not and their status on competitors"""
        JSONResp: dict[dict] = self.api.get('hosts/status')   
        if self.api._convert_special_types:
            for host in JSONResp:
                host['check_time'] = datetime.strptime(host['check_time'], DATE_JSON_FORMAT)
                if host.get('competitor_status'):
                    for competitor in host['competitor_status']:
                        competitor['check_time'] = datetime.strptime(competitor['check_time'], DATE_JSON_FORMAT)
            
        return JSONResp

    def regex(self) -> list:
        """Get all supported links Regex, useful to find supported links inside a document. This request does not require authentication"""
        return self.api.get('hosts/regex')  

    def regex_folder(self) -> list:
        """Get all supported folder Regex, useful to find supported links inside a document. This request does not require authentication"""
        return self.api.get('hosts/regexFolder')  

    def domains(self):
        """Get all hoster domains supported on the service. This request does not require authentication"""
        return self.api.get('hosts/domains')  

class Settings:
    def __init__(self, api: RealDebridApi):
        self.api = api

    def get(self):
        """Get current user settings with possible values to update"""
        return self.api.get('settings')
    
    def update(self, setting_name: str, setting_value:str):
        """Update a user setting, returns 204 HTTP code"""
        return self.api.post('settings/update', setting_name=setting_name, setting_value=setting_value)
    
    def convert_points(self):
        """Convert fidelity points, returns 204 HTTP code"""
        return self.api.post('settings/convertPoints')            

    def change_password(self):
        """Send the verification email to change the password, returns 204 HTTP code"""
        return self.api.post('settings/changePassword')      

    def avatar_file(self, filepath:Path):
        """Upload a new user avatar image, returns 204 HTTP code"""
        return self.api.put('settings/avatarFile', filepath=filepath)
    
    def avatar_delete(self):
        """Reset user avatar image to default, returns 204 HTTP code"""
        return self.api.delete('settings/avatarDelete')

