from typing import TYPE_CHECKING, Optional

from cyberdrop_dl.managers.real_debrid.api import RealDebridApi, RATE_LIMIT
from cyberdrop_dl.managers.real_debrid.errors import RealDebridError
from cyberdrop_dl.utils.utilities import log
import re
from dataclasses import field
from yarl import URL
from re import Pattern
import warnings

warnings.simplefilter(action='ignore', category=FutureWarning)

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager

FOLDER_AS_PART = {'folder','folders','dir'}
FOLDER_AS_QUERY = {'sharekey'}

class RealDebridManager:
    def __init__(self, manager: 'Manager'):
        self.manager = manager
        self.__api_token = self.manager.config_manager.authentication_data['RealDebrid']['realdebrid_api_key']
        self.enabled = bool(self.__api_token)
        self.file_regex: Pattern = field(init=False)
        self.folder_regex: Pattern = field(init=False)
        self.supported_regex: Pattern = field(init=False)
        self.api: RealDebridApi = field(init=False)
        self._folder_guess_functions = [
            self._guess_folder_by_part, 
            self._guess_folder_by_query
            ]

    async def startup(self) -> None:
        """Startup process for Real Debrid manager"""
        try:
            self.api = RealDebridApi(self.__api_token, True)
            file_regex = [pattern[1:-1] for pattern in self.api.hosts.regex()]
            folder_regex = [pattern[1:-1] for pattern in self.api.hosts.regex_folder()]
            regex = "|".join(file_regex + folder_regex)
            file_regex = "|".join(file_regex) 
            folder_regex = "|".join(folder_regex)             
            self.supported_regex = re.compile(regex)
            self.file_regex = re.compile(file_regex)
            self.folder_regex = re.compile(folder_regex)    
        except RealDebridError as e:
            await log(f"Failed RealDebrid setup: {e.error}", 40)
            self.enabled = False  

    async def is_supported_folder(self, url: URL) -> bool:
        match = self.folder_regex.search(str(url))
        return bool(match)
    
    async def is_supported_file(self, url: URL) -> bool:
        match = self.file_regex.search(str(url))
        return bool(match)

    async def is_supported(self, url: URL) -> bool:
        match = self.supported_regex.search(str(url))
        return bool(match) or 'real-debrid' in url.host.lower()

    async def unrestrict_link(self, url: URL, password: Optional[str] = None) -> URL:
        return self.api.unrestrict.link(url, password).get('download')

    async def unrestrict_folder(self, url: URL) -> list [URL]:
        return self.api.unrestrict.folder(url)
    
    async def _guess_folder_by_part(self, url: URL):
        folder = None
        for word in FOLDER_AS_PART:
            if word in url.parts:
                index = url.parts.index(word)
                if index + 1 < len(url.parts):
                    return url.parts[index + 1]
        return folder
        
    async def _guess_folder_by_query(self, url: URL):
        for word in FOLDER_AS_QUERY:
            folder = url.query.get(word)
            if folder:
                break
        return folder
        
    async def guess_folder(self, url:URL ) -> str:
        for guess_function in self._folder_guess_functions:
            folder = await guess_function(url)
            if folder:
                return folder
        return url.path
        
