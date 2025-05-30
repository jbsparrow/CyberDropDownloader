# This file incorporates work covered by the Apache License 2.0,
#
# Original Apache repo: https://github.com/odwyersoftware/mega.py
#
# Original Apache License 2.0 Header:
#
# Copyright 2019 richardARPANET
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#
# Modifications 04-2025, licensed under the GNU General Public License version 3 (GPLv3):
#
# - Fixed login request parameters for the new v2 accounts
# - Fixed RSA key computation.
# - Fixed attribute encoding issues.
# - Fixed AES CBC decryption without proper padding.
# - Fixed filename encoding detection.
# - Fixed incomplete node information when querying a folder.
# - Fixed permission error caused by concurrent access to the same file.
# - Simplified node attributes proccessing logic by deprecating deduntan tuple Node class
# - Added xhashcash computation to handle mega challenges while logging.
# - Replaced all code logic with asynchronous methods.
# - Added support for downloading entire folders.
# - Updated primary domain, mega.co.nz to mega.nz.
# - Defined custom classes for nodes, file and folders.
# - Added type anotations
# - Used memory view to increase performance of MAC computation.
# - Update syntax and dependencies to support for Python 3.9+.
# - Separated API and client logic.
# - Added a build_file_system method.
# - Replaced the third-party pathlib library with the built-in pathlib


from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import math
import random
import string
import struct
import time
from enum import IntEnum
from functools import partial
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, NotRequired, TypeAlias, TypedDict, cast

import aiofiles
import aiohttp
from aiohttp import ClientSession, ClientTimeout
from Crypto.Cipher import AES
from Crypto.Math.Numbers import Integer
from Crypto.PublicKey import RSA
from Crypto.Util import Counter

from cyberdrop_dl.clients.download_client import DownloadClient
from cyberdrop_dl.downloader.downloader import Downloader
from cyberdrop_dl.exceptions import CDLBaseError, DownloadError, SlowDownloadError
from cyberdrop_dl.types import AnyDict, U32Int, U32IntArray, U32IntSequence
from cyberdrop_dl.utils.logger import log

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

    from yarl import URL

    from cyberdrop_dl.data_structures.url_objects import MediaItem
    from cyberdrop_dl.managers.manager import Manager


class MegaNzError(CDLBaseError): ...


class ValidationError(MegaNzError):
    """Error in validation stage"""


ERROR_CODES = {
    -1: "EINTERNAL (-1): An internal error has occurred. Please submit a bug report, detailing the exact circumstances in which this error occurred.",
    -2: "EARGS (-2): You have passed invalid arguments to this command.",
    -3: "EAGAIN (-3): A temporary congestion or server malfunction prevented your request from being processed. No data was altered",
    -4: "ERATELIMIT (-4): You have exceeded your command weight per time quota. Please wait a few seconds, then try again (this should never happen in sane real-life applications).",
    -5: "EFAILED (-5): The upload failed. Please restart it from scratch.",
    -6: "ETOOMANY (-6): Too many concurrent IP addresses are accessing this upload target URL.",
    -7: "ERANGE (-7): The upload file packet is out of range or not starting and ending on a chunk boundary.",
    -8: "EEXPIRED (-8): The upload target URL you are trying to access has expired. Please request a fresh one.",
    -9: "ENOENT (-9): Object (typically, node or user) not found. Wrong password?",
    -10: "ECIRCULAR (-10): Circular linkage attempted",
    -11: "EACCESS (-11): Access violation (e.g., trying to write to a read-only share)",
    -12: "EEXIST (-12): Trying to create an object that already exists",
    -13: "EINCOMPLETE (-13): Trying to access an incomplete resource",
    -14: "EKEY (-14): A decryption operation failed (never returned by the API)",
    -15: "ESID (-15): Invalid or expired user session, please relogin",
    -16: "EBLOCKED (-16): User blocked",
    -17: "EOVERQUOTA (-17): Request over quota",
    -18: "ETEMPUNAVAIL (-18): Resource temporarily not available, please try again later",
    -19: "ETOOMANYCONNECTIONS (-19)",
    -24: "EGOINGOVERQUOTA (-24)",
    -25: "EROLLEDBACK (-25)",
    -26: "EMFAREQUIRED (-26): Multi-Factor Authentication Required",
    -27: "EMASTERONLY (-27)",
    -28: "EBUSINESSPASTDUE (-28)",
    -29: "EPAYWALL (-29): ODQ paywall state",
    -400: "ETOOERR (-400)",
    -401: "ESHAREROVERQUOTA (-401)",
}


class RequestError(MegaNzError):
    """
    Error in API request
    """

    def __init__(self, msg: str | int) -> None:
        self.code = code = msg if isinstance(msg, int) else None
        if code:
            self.message = ERROR_CODES[code]
        else:
            self.message = str(msg)

    def __str__(self) -> str:
        return self.message


CHUNK_BLOCK_LEN = 16  # Hexadecimal
EMPTY_IV = b"\0" * CHUNK_BLOCK_LEN


U32IntTupleArray: TypeAlias = tuple[U32Int, ...]


class Chunk(NamedTuple):
    offset: int
    size: int


class Attributes(TypedDict):
    n: str  # Name


class NodeType(IntEnum):
    DUMMY = -1
    FILE = 0
    FOLDER = 1
    ROOT_FOLDER = 2
    INBOX = 3
    TRASH = 4


class Node(TypedDict):
    t: NodeType
    h: str  # Id
    p: str  # Parent Id
    a: str  # Encrypted attributes (within this: 'n' Name)
    k: str  # Node key
    u: str  # User Id
    s: int  # Size
    ts: int  # Timestamp
    g: str  # Access URL
    k: str  # Public access key (parent folder + file)

    #  Non standard properties, only used internally
    attributes: Attributes  # Decrypted attributes
    k_decrypted: U32IntTupleArray
    key_decrypted: U32IntTupleArray  # Decrypted access key (for folders, its values if the same as 'k_decrypted')


class FileOrFolder(Node):
    su: NotRequired[str]  # Shared user Id, only present present in shared files / folder
    sk: NotRequired[str]  # Shared key, only present present in shared (public) files / folder

    #  Non standard properties, only used internally
    iv: U32IntTupleArray
    meta_mac: U32IntTupleArray
    sk_decrypted: U32IntTupleArray


class File(FileOrFolder):
    at: str  # File specific attributes (encrypted)


class Folder(FileOrFolder):
    f: list[FileOrFolder]  # Children (files or folders)
    ok: list[FileOrFolder]
    s: list[FileOrFolder]


SharedKey = dict[str, U32IntTupleArray]  # Mapping: (recipient) User Id ('u') -> decrypted value of shared key ('sk')
SharedkeysDict = dict[str, SharedKey]  # Mapping: (owner) Shared User Id ('su') -> SharedKey
FilesMapping = dict[str, FileOrFolder]  # key is parent_id ('p')


class DecryptData(NamedTuple):
    iv: U32IntTupleArray
    k: U32IntTupleArray
    meta_mac: U32IntTupleArray
    file_size: int = 0


def pad_bytes(data: bytes, length: int = CHUNK_BLOCK_LEN) -> bytes:
    """
    Pads a bytes-like object with null bytes to a multiple of the specified length.

    Args:
        data: The bytes-like object to pad (bytes or memoryview).
        lenght: The block size to pad to. Defaults to 16.

    Returns:
        A new bytes object that is padded with null bytes such that its length is a multiple of 'length'.
    """

    if len(data) % length:
        padding = b"\0" * (length - len(data) % length)
        if isinstance(data, memoryview):
            return data.tobytes() + padding
        return data + padding
    return data


def random_u32int() -> U32Int:
    return random.randint(0, 0xFFFFFFFF)


def _aes_cbc_encrypt(data: bytes, key: bytes) -> bytes:
    return AES.new(key, AES.MODE_CBC, EMPTY_IV).encrypt(data)


def _aes_cbc_decrypt(data: bytes, key: bytes) -> bytes:
    return AES.new(key, AES.MODE_CBC, EMPTY_IV).decrypt(data)


def _aes_cbc_encrypt_a32(data: U32IntSequence, key: U32IntSequence) -> U32IntTupleArray:
    return str_to_a32(_aes_cbc_encrypt(a32_to_bytes(data), a32_to_bytes(key)))


def _aes_cbc_decrypt_a32(data: U32IntSequence, key: U32IntSequence) -> U32IntTupleArray:
    return str_to_a32(_aes_cbc_decrypt(a32_to_bytes(data), a32_to_bytes(key)))


def make_hash(string: str, aeskey: U32IntSequence) -> str:
    s32 = str_to_a32(string)
    h32 = [0, 0, 0, 0]
    for i in range(len(s32)):
        h32[i % 4] ^= s32[i]
    for _ in range(0x4000):
        h32 = _aes_cbc_encrypt_a32(h32, aeskey)
    return a32_to_base64((h32[0], h32[2]))


def prepare_key(arr: U32IntArray) -> U32IntArray:
    pkey: U32IntArray = [0x93C467E3, 0x7DB0C7A4, 0xD1BE3F81, 0x0152CB56]
    for _ in range(0x10000):
        for j in range(0, len(arr), 4):
            key: U32IntArray = [0, 0, 0, 0]
            for i in range(4):
                if i + j < len(arr):
                    key[i] = arr[i + j]
            pkey = _aes_cbc_encrypt_a32(pkey, key)
    return pkey


def encrypt_key(array: U32IntSequence, key: U32IntSequence) -> U32IntTupleArray:
    # this sum, which is applied to a generator of tuples, actually flattens the output list of lists of that generator
    # i.e. it's equivalent to tuple([item for t in generatorOfLists for item in t])

    return sum((_aes_cbc_encrypt_a32(array[index : index + 4], key) for index in range(0, len(array), 4)), ())


def decrypt_key(array: U32IntSequence, key: U32IntSequence) -> U32IntTupleArray:
    return sum((_aes_cbc_decrypt_a32(array[index : index + 4], key) for index in range(0, len(array), 4)), ())


def encrypt_attr(attr_dict: dict, key: U32IntSequence) -> bytes:
    attr: bytes = f"MEGA{json.dumps(attr_dict)}".encode()
    attr = pad_bytes(attr)
    return _aes_cbc_encrypt(attr, a32_to_bytes(key))


def decrypt_attr(attr: bytes, key: U32IntSequence) -> AnyDict:
    attr_bytes = _aes_cbc_decrypt(attr, a32_to_bytes(key))
    try:
        attr_str = attr_bytes.decode("utf-8").rstrip("\0")
    except UnicodeDecodeError:
        attr_str = attr_bytes.decode("latin-1").rstrip("\0")
    if attr_str.startswith('MEGA{"'):
        start = 4
        end = attr_str.find("}") + 1
        if end >= 1:
            return json.loads(attr_str[start:end])
        else:
            raise RuntimeError(f"Unable to properly decode filename, raw content is: {attr_str}")
    else:
        return {}


def a32_to_bytes(array: U32IntSequence) -> bytes:
    return struct.pack(f">{len(array):.0f}I", *array)


def str_to_a32(bytes_or_str: str | bytes) -> U32IntTupleArray:
    if isinstance(bytes_or_str, str):
        bytes_ = bytes_or_str.encode()
    else:
        assert isinstance(bytes_or_str, bytes)
        bytes_ = bytes_or_str

    # pad to multiple of 4
    bytes_ = pad_bytes(bytes_, length=4)
    return struct.unpack(f">{(len(bytes_) / 4):.0f}I", bytes_)


def mpi_to_int(data: bytes) -> int:
    """
    A Multi-precision integer (mpi) is encoded as a series of bytes in big-endian
    order. The first two bytes are a header which tell the number of bits in
    the integer. The rest of the bytes are the integer.
    """
    return int(binascii.hexlify(data[2:]), CHUNK_BLOCK_LEN)


def base64_url_decode(data: str) -> bytes:
    data += "=="[(2 - len(data) * 3) % 4 :]
    for search, replace in (("-", "+"), ("_", "/"), (",", "")):
        data = data.replace(search, replace)
    return base64.b64decode(data)


def base64_to_a32(string: str) -> U32IntTupleArray:
    return str_to_a32(base64_url_decode(string))


def base64_url_encode(data: bytes) -> str:
    data_bytes = base64.b64encode(data)
    data_str = data_bytes.decode()
    for search, replace in (("+", "-"), ("/", "_"), ("=", "")):
        data_str = data_str.replace(search, replace)
    return data_str


def a32_to_base64(array: U32IntSequence) -> str:
    return base64_url_encode(a32_to_bytes(array))


def get_chunks(size: int) -> Generator[Chunk]:
    # generates a list of chunks (offset, chunk_size), where offset refers to the file initial position
    offset = 0
    current_size = init_size = 0x20000
    while offset + current_size < size:
        yield Chunk(offset, current_size)
        offset += current_size
        if current_size < 0x100000:
            current_size += init_size
    yield Chunk(offset, size - offset)


def decrypt_rsa_key(private_key: bytes) -> RSA.RsaKey:
    # The private_key contains 4 MPI integers concatenated together.
    rsa_private_key = [0, 0, 0, 0]
    for i in range(4):
        # An MPI integer has a 2-byte header which describes the number
        # of bits in the integer.
        bitlength = (private_key[0] * 256) + private_key[1]
        bytelength = math.ceil(bitlength / 8)
        # Add 2 bytes to accommodate the MPI header
        bytelength += 2
        rsa_private_key[i] = mpi_to_int(private_key[:bytelength])
        private_key = private_key[bytelength:]

    first_factor_p = rsa_private_key[0]
    second_factor_q = rsa_private_key[1]
    private_exponent_d = rsa_private_key[2]
    crt_coeficient_u = rsa_private_key[3]
    rsa_modulus_n = first_factor_p * second_factor_q
    phi = (first_factor_p - 1) * (second_factor_q - 1)
    public_exponent_e = int(Integer(private_exponent_d).inverse(phi))

    rsa_components = (
        rsa_modulus_n,
        public_exponent_e,
        private_exponent_d,
        first_factor_p,
        second_factor_q,
        crt_coeficient_u,
    )

    rsa_key = RSA.construct(rsa_components, consistency_check=True)
    return rsa_key


async def generate_hashcash_token(challenge: str) -> str:
    parts = challenge.split(":")
    version_str, easiness_str, _, token_str = parts
    version = int(version_str)
    if version != 1:
        raise MegaNzError("hashcash challenge is not version 1 [Mega]")

    easiness = int(easiness_str)
    base = ((easiness & 63) << 1) + 1
    shifts = (easiness >> 6) * 7 + 3
    threshold = base << shifts
    token = base64_url_decode(token_str)
    buffer = bytearray(4 + 262144 * 48)
    for i in range(262144):
        buffer[4 + i * 48 : 4 + (i + 1) * 48] = token

    def hash_val(val: bytes):
        return hashlib.sha256(buffer).digest()

    while True:
        digest = await asyncio.to_thread(hash_val, buffer)
        view = struct.unpack(">I", digest[:4])[0]  # big-endian uint32
        if view <= threshold:
            return f"1:{token_str}:{base64_url_encode(buffer[:4])}"

        # Increment the first 4 bytes as a little-endian integer
        for j in range(4):
            buffer[j] = (buffer[j] + 1) & 0xFF
            if buffer[j] != 0:
                break


VALID_REQUEST_ID_CHARS = string.ascii_letters + string.digits


class MegaApi:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.schema = "https"
        self.domain = "mega.nz"
        self.api_domain = "g.api.mega.co.nz"  # api still uses the old mega.co.nz domain
        self.timeout = ClientTimeout(160)
        self.sid: str | None = None
        self.sequence_num: U32Int = random_u32int()
        self.request_id: str = "".join(random.choice(VALID_REQUEST_ID_CHARS) for _ in range(10))
        self.user_agent = manager.config_manager.global_settings_data.general.user_agent
        self.default_headers = {"Content-Type": "application/json", "User-Agent": self.user_agent}
        self.session = ClientSession()
        self.entrypoint = f"{self.schema}://{self.api_domain}/cs"
        self.logged_in = False
        self.root_id: str = ""
        self.inbox_id: str = ""
        self.trashbin_id: str = ""
        self._files = {}

    async def close(self):
        await self.session.close()

    async def request(self, data_input: list[AnyDict] | AnyDict, add_params: AnyDict | None = None) -> Any:
        add_params = add_params or {}
        params: AnyDict = {"id": self.sequence_num} | add_params
        self.sequence_num += 1
        if self.sid:
            params["sid"] = self.sid

        # ensure input data is a list
        if not isinstance(data_input, list):
            data = [data_input]
        else:
            data: list[AnyDict] = data_input

        response = await self.session.post(
            self.entrypoint, params=params, json=data, timeout=self.timeout, headers=self.default_headers
        )

        # Since around feb 2025, MEGA requires clients to solve a challenge during each login attempt.
        # When that happens, initial responses returns "402 Payment Required".
        # Challenge is inside the `X-Hashcash` header.
        # We need to solve the challenge and re-made the request with same params + the computed token
        # See:  https://github.com/gpailler/MegaApiClient/issues/248#issuecomment-2692361193

        if xhashcash_challenge := response.headers.get("X-Hashcash"):
            log("Solving xhashcash login challenge, this could take a few seconds...")
            xhashcash_token = await generate_hashcash_token(xhashcash_challenge)
            headers = self.default_headers | {"X-Hashcash": xhashcash_token}
            response = await self.session.post(
                self.entrypoint, params=params, json=data, timeout=self.timeout, headers=headers
            )

        if xhashcash_challenge := response.headers.get("X-Hashcash"):
            # Computed token failed
            msg = f"Login failed. Mega requested a proof of work with xhashcash: {xhashcash_challenge}"
            raise RequestError(msg)

        json_resp: list[Any] | list[int] | int = await response.json()

        def handle_int_resp(int_resp: int):
            if int_resp == 0:
                return int_resp
            if int_resp == -3:
                msg = "Request failed, retrying"
                raise RuntimeError(msg)
            raise RequestError(int_resp)

        if isinstance(json_resp, int):
            return handle_int_resp(json_resp)
        elif not isinstance(json_resp, list):
            raise RequestError(f"Unknown response: {json_resp:r}")
        elif json_resp:
            first = json_resp[0]
            if isinstance(first, int):
                return handle_int_resp(first)
            return first
        else:
            raise RequestError(f"Unknown response: {json_resp:r}")

    async def login(self, email: str | None = None, password: str | None = None):
        if email and password:
            await self._login_user(email, password)
        else:
            await self.login_anonymous()
        _ = await self.get_files()  # This is to set the special folders id
        self.logged_in = True
        log("Login complete [Mega]")
        return self

    def _process_login(self, resp: AnyDict, password: U32IntArray):
        encrypted_master_key = base64_to_a32(resp["k"])
        self.master_key = decrypt_key(encrypted_master_key, password)
        if b64_tsid := resp.get("tsid"):
            tsid = base64_url_decode(b64_tsid)
            key_encrypted = a32_to_bytes(encrypt_key(str_to_a32(tsid[:16]), self.master_key))
            if key_encrypted == tsid[-16:]:
                self.sid = resp["tsid"]

        elif b64_csid := resp.get("csid"):
            encrypted_sid = mpi_to_int(base64_url_decode(b64_csid))
            encrypted_private_key = base64_to_a32(resp["privk"])
            private_key = a32_to_bytes(decrypt_key(encrypted_private_key, self.master_key))
            rsa_key = decrypt_rsa_key(private_key)

            # TODO: Investigate how to decrypt using the current pycryptodome library.
            # The _decrypt method of RSA is deprecated and no longer available.
            # The documentation suggests using Crypto.Cipher.PKCS1_OAEP,
            # but the algorithm differs and requires bytes as input instead of integers.
            decrypted_sid = int(rsa_key._decrypt(encrypted_sid))  # type: ignore
            sid_hex = f"{decrypted_sid:x}"
            sid_bytes = bytes.fromhex("0" + sid_hex if len(sid_hex) % 2 else sid_hex)
            sid = base64_url_encode(sid_bytes[:43])
            self.sid = sid

    async def _login_user(self, email: str, password: str) -> None:
        log("Logging in user...")
        email = email.lower()
        get_user_salt_resp: dict = await self.request({"a": "us0", "user": email})

        if b64_salt := get_user_salt_resp.get("s"):
            # v2 user account
            user_salt = base64_to_a32(b64_salt)
            pbkdf2_key = hashlib.pbkdf2_hmac(
                hash_name="sha512",
                password=password.encode(),
                salt=a32_to_bytes(user_salt),
                iterations=100000,
                dklen=32,
            )
            password_aes = str_to_a32(pbkdf2_key[:16])
            user_hash = base64_url_encode(pbkdf2_key[-16:])

        else:
            # v1 user account
            password_aes = prepare_key(str_to_a32(password))
            user_hash = make_hash(email, password_aes)

        resp = await self.request({"a": "us", "user": email, "uh": user_hash})
        self._process_login(resp, password_aes)

    async def login_anonymous(self) -> None:
        log("Logging in anonymous temporary user...")
        master_key = [random_u32int()] * 4
        password_key = [random_u32int()] * 4
        session_self_challenge = [random_u32int()] * 4
        ts_array = a32_to_bytes(session_self_challenge) + a32_to_bytes(encrypt_key(session_self_challenge, master_key))

        user: str = await self.request(
            {
                "a": "up",
                "k": a32_to_base64(encrypt_key(master_key, password_key)),
                "ts": base64_url_encode(ts_array),
            }
        )

        resp = await self.request({"a": "us", "user": user})
        self._process_login(resp, password_key)

    def _process_node(self, file: Node, shared_keys: SharedkeysDict) -> Node:
        if file["t"] == NodeType.FILE or file["t"] == NodeType.FOLDER:
            file = cast("FileOrFolder", file)
            keys = dict(keypart.split(":", 1) for keypart in file["k"].split("/") if ":" in keypart)
            uid = file["u"]
            key = None
            # my objects
            if uid in keys:
                key = decrypt_key(base64_to_a32(keys[uid]), self.master_key)
            # shared folders
            elif "su" in file and "sk" in file and ":" in file["k"]:
                shared_key = decrypt_key(base64_to_a32(file["sk"]), self.master_key)
                key = decrypt_key(base64_to_a32(keys[file["h"]]), shared_key)
                if file["su"] not in shared_keys:
                    shared_keys[file["su"]] = {}
                shared_keys[file["su"]][file["h"]] = shared_key
            # shared files
            elif file["u"] and file["u"] in shared_keys:
                for hkey in shared_keys[file["u"]]:
                    shared_key = shared_keys[file["u"]][hkey]
                    if hkey in keys:
                        key = keys[hkey]
                        key = decrypt_key(base64_to_a32(key), shared_key)
                        break
            if file["h"] and file["h"] in shared_keys.get("EXP", ()):
                shared_key = shared_keys["EXP"][file["h"]]
                encrypted_key = str_to_a32(base64_url_decode(file["k"].split(":")[-1]))
                key = decrypt_key(encrypted_key, shared_key)
                file["sk_decrypted"] = shared_key

            if key is not None:
                # file
                if file["t"] == NodeType.FILE:
                    file = cast("File", file)
                    k = (key[0] ^ key[4], key[1] ^ key[5], key[2] ^ key[6], key[3] ^ key[7])
                    file["iv"] = key[4:6] + (0, 0)
                    file["meta_mac"] = key[6:8]
                # folder
                else:
                    k = key

                file["key_decrypted"] = key
                file["k_decrypted"] = k
                attributes_bytes = base64_url_decode(file["a"])
                attributes = decrypt_attr(attributes_bytes, k)
                file["attributes"] = cast("Attributes", attributes)

            # other => wrong object
            elif file["k"] == "":
                file = cast("Node", file)
                file["attributes"] = {"n": "Unknown Object"}

        elif file["t"] == NodeType.ROOT_FOLDER:
            self.root_id: str = file["h"]
            file["attributes"] = {"n": "Cloud Drive"}

        elif file["t"] == NodeType.INBOX:
            self.inbox_id = file["h"]
            file["attributes"] = {"n": "Inbox"}

        elif file["t"] == NodeType.TRASH:
            self.trashbin_id = file["h"]
            file["attributes"] = {"n": "Trash Bin"}

        return file

    def _init_shared_keys(self, files: Folder, shared_keys: SharedkeysDict) -> None:
        """
        Init shared key not associated with a user.
        Seems to happen when a folder is shared,
        some files are exchanged and then the
        folder is un-shared.
        Keys are stored in files['s'] and files['ok']
        """
        shared_key: SharedKey = {}
        for ok_file in files["ok"]:
            decrypted_shared_key = decrypt_key(base64_to_a32(ok_file["k"]), self.master_key)
            shared_key[ok_file["h"]] = decrypted_shared_key
        for s_file in files["s"]:
            if s_file["u"] not in shared_keys:
                shared_keys[s_file["u"]] = {}
            if s_file["h"] in shared_key:
                shared_keys[s_file["u"]][s_file["h"]] = shared_key[s_file["h"]]
        self.shared_keys = shared_keys

    async def get_files(self) -> FilesMapping:
        if self._files:
            return self._files
        files_dict: FilesMapping = {}
        async for node in self._get_nodes():
            if node["attributes"]:
                file = cast("File", node)
                files_dict[file["h"]] = file
        self._files = files_dict
        return files_dict

    async def _get_nodes(self) -> AsyncGenerator[Node]:
        files: Folder = await self.request({"a": "f", "c": 1, "r": 1})
        shared_keys: SharedkeysDict = {}
        self._init_shared_keys(files, shared_keys)
        for index, node in enumerate(files["f"], 1):
            yield self._process_node(node, shared_keys)
            if index % 100 == 0:
                await asyncio.sleep(0)

    async def _get_nodes_in_shared_folder(self, folder_id: str) -> AsyncGenerator[Node]:
        files: Folder = await self.request(
            {"a": "f", "c": 1, "ca": 1, "r": 1},
            {"n": folder_id},
        )
        for index, node in enumerate(files["f"], 1):
            yield self._process_node(node, self.shared_keys)
            if index % 100 == 0:
                await asyncio.sleep(0)

    async def get_nodes_public_folder(self, folder_id: str, b64_share_key: str) -> dict[str, FileOrFolder]:
        shared_key = base64_to_a32(b64_share_key)

        async def prepare_nodes():
            async for node in self._get_nodes_in_shared_folder(folder_id):
                node = cast("FileOrFolder", node)
                encrypted_key = base64_to_a32(node["k"].split(":")[1])
                key = decrypt_key(encrypted_key, shared_key)
                if node["t"] == NodeType.FILE:
                    k = (key[0] ^ key[4], key[1] ^ key[5], key[2] ^ key[6], key[3] ^ key[7])
                elif node["t"] == NodeType.FOLDER:
                    k = key

                iv: U32IntSequence = key[4:6] + (0, 0)
                meta_mac: U32IntTupleArray = key[6:8]

                attrs = decrypt_attr(base64_url_decode(node["a"]), k)
                node["attributes"] = cast("Attributes", attrs)
                node["k_decrypted"] = k
                node["iv"] = iv
                node["meta_mac"] = meta_mac
                yield node

        nodes = {node["h"]: node async for node in prepare_nodes()}
        return nodes

    async def _build_file_system(self, nodes_map: dict[str, Node], root_ids: list[str]) -> dict[Path, Node]:
        """Builds a flattened dictionary representing a file system from a list of items.

        Returns:
            A 1-level dictionary where the each keys is the full path to a file/folder, and each value is the actual file/folder
        """

        path_mapping: dict[Path, Node] = {}
        parents_mapping: dict[str, list[Node]] = {}

        for _, item in nodes_map.items():
            parent_id = item["p"]
            if parent_id not in parents_mapping:
                parents_mapping[parent_id] = []
            parents_mapping[parent_id].append(item)

        async def build_tree(parent_id: str, current_path: Path) -> None:
            for item in parents_mapping.get(parent_id, []):
                item_path = current_path / item["attributes"]["n"]
                path_mapping[item_path] = item

                if item["t"] == NodeType.FOLDER:
                    await build_tree(item["h"], item_path)

            await asyncio.sleep(0)

        for root_id in root_ids:
            root_item = nodes_map[root_id]
            name = root_item["attributes"]["n"]
            path = Path(name if name != "Cloud Drive" else ".")
            path_mapping[path] = root_item
            await build_tree(root_id, path)

        sorted_mapping = dict(sorted(path_mapping.items()))
        return sorted_mapping


class MegaDownloadClient(DownloadClient):
    def __init__(self, api: MegaApi) -> None:
        super().__init__(api.manager, api.manager.client_manager)
        self.api = api
        self.decrypt_mapping: dict[URL, DecryptData] = {}

    async def close(self):
        await self.api.close()

    def _decrypt_chunks(
        self,
        iv: U32IntTupleArray,
        k_decrypted: U32IntTupleArray,
        meta_mac: U32IntTupleArray,
    ) -> Generator[bytes, bytes, None]:
        """
        Decrypts chunks of data received via `send()` and yields the decrypted chunks.
        It decrypts chunks indefinitely until a sentinel value (`None`) is sent.

        NOTE: You MUST send `None` after decrypting every chunk to execute the mac check

        Args:
            iv (AnyArray):  Initialization vector (iv) as a list or tuple of two 32-bit unsigned integers.
            k_decrypted (TupleArray):  Decryption key as a tuple of four 32-bit unsigned integers.
            meta_mac (AnyArray):  The expected MAC value of the final file.

        Yields:
            bytes:  Decrypted chunk of data. The first `yield` is a blank (`b''`) to initialize generator.

        """
        k_bytes = a32_to_bytes(k_decrypted)
        counter = Counter.new(128, initial_value=((iv[0] << 32) + iv[1]) << 64)
        aes = AES.new(k_bytes, AES.MODE_CTR, counter=counter)

        # mega.nz improperly uses CBC as a MAC mode, so after each chunk
        # the computed mac_bytes are used as IV for the next chunk MAC accumulation
        mac_bytes = b"\0" * 16
        mac_encryptor = AES.new(k_bytes, AES.MODE_CBC, mac_bytes)
        iv_bytes = a32_to_bytes([iv[0], iv[1], iv[0], iv[1]])
        raw_chunk = yield b""
        while True:
            if raw_chunk is None:
                break
            decrypted_chunk = aes.decrypt(raw_chunk)
            raw_chunk = yield decrypted_chunk
            encryptor = AES.new(k_bytes, AES.MODE_CBC, iv_bytes)

            # take last 16-N bytes from chunk (with N between 1 and 16, including extremes)
            mem_view = memoryview(decrypted_chunk)  # avoid copying memory for the entire chunk when slicing
            modchunk = len(decrypted_chunk) % CHUNK_BLOCK_LEN
            if modchunk == 0:
                # ensure we reserve the last 16 bytes anyway, we have to feed them into mac_encryptor
                modchunk = CHUNK_BLOCK_LEN

            # pad last block to 16 bytes
            last_block = pad_bytes(mem_view[-modchunk:])
            rest_of_chunk = mem_view[:-modchunk]
            _ = encryptor.encrypt(rest_of_chunk)
            input_to_mac = encryptor.encrypt(last_block)
            mac_bytes = mac_encryptor.encrypt(input_to_mac)

        file_mac = str_to_a32(mac_bytes)
        computed_mac = file_mac[0] ^ file_mac[1], file_mac[2] ^ file_mac[3]
        if computed_mac != meta_mac:
            raise RuntimeError("Mismatched mac")

    async def _append_content(
        self,
        media_item: MediaItem,
        content: aiohttp.StreamReader,
        update_progress: partial,
    ) -> None:
        """Appends content to a file."""

        check_free_space = partial(self.manager.storage_manager.check_free_space, media_item)
        await check_free_space()

        media_item.partial_file.parent.mkdir(parents=True, exist_ok=True)  # type: ignore
        media_item.partial_file.unlink(missing_ok=True)  # type: ignore # We can't resume
        media_item.partial_file.touch()  # type: ignore

        last_slow_speed_read = None

        def check_download_speed():
            nonlocal last_slow_speed_read
            speed = self.manager.progress_manager.file_progress.get_speed(media_item.task_id)  # type: ignore
            if speed > self.download_speed_threshold:
                last_slow_speed_read = None
            elif not last_slow_speed_read:
                last_slow_speed_read = time.perf_counter()
            elif time.perf_counter() - last_slow_speed_read > self.slow_download_period:
                raise SlowDownloadError(origin=media_item)

        data = self.decrypt_mapping[media_item.url]
        chunk_decryptor = self._decrypt_chunks(data.iv, data.k, data.meta_mac)
        _ = next(chunk_decryptor)  # Prime chunk decryptor

        async with aiofiles.open(media_item.partial_file, mode="ab") as f:  # type: ignore
            for _, chunk_size in get_chunks(data.file_size):
                await self.manager.states.RUNNING.wait()
                raw_chunk = await content.readexactly(chunk_size)
                decrypted_chunk: bytes = chunk_decryptor.send(raw_chunk)
                await check_free_space()
                chunk_size = len(decrypted_chunk)
                await self.client_manager.speed_limiter.acquire(chunk_size)
                await f.write(decrypted_chunk)
                update_progress(chunk_size)

                if self.download_speed_threshold:
                    check_download_speed()

        if not content.total_bytes and not media_item.partial_file.stat().st_size:  # type: ignore
            media_item.partial_file.unlink()  # type: ignore
            raise DownloadError(status=HTTPStatus.INTERNAL_SERVER_ERROR, message="File is empty")
        try:
            # Stop chunk decryptor and do a mac integrity check
            chunk_decryptor.send(None)  # type: ignore
        except StopIteration:
            pass


class MegaDownloader(Downloader):
    def __init__(self, api: MegaApi, domain: str):
        self.client: MegaDownloadClient
        super().__init__(api.manager, domain)
        self.api = api

    def startup(self) -> None:
        """Starts the downloader."""
        self.client = MegaDownloadClient(self.api)
        self._semaphore = asyncio.Semaphore(self.manager.download_manager.get_download_limit(self.domain))

        self.manager.path_manager.download_folder.mkdir(parents=True, exist_ok=True)
        if self.manager.config_manager.settings_data.sorting.sort_downloads:
            self.manager.path_manager.sorted_folder.mkdir(parents=True, exist_ok=True)

    def register(
        self, url: URL, iv: U32IntTupleArray, k_decrypted: U32IntTupleArray, meta_mac: U32IntTupleArray, file_size: int
    ) -> None:
        self.client.decrypt_mapping[url] = DecryptData(iv, k_decrypted, meta_mac, file_size)
