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
# - Simplified node attributes processing logic by deprecating deduntan tuple Node class
# - Added xhashcash computation to handle mega challenges while logging.
# - Replaced all code logic with asynchronous methods.
# - Added support for downloading entire folders.
# - Updated primary domain, mega.co.nz to mega.nz.
# - Defined custom classes for nodes, file and folders.
# - Added type annotations
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
from collections.abc import Callable, Coroutine, Sequence
from enum import IntEnum
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, NamedTuple, NotRequired, TypeAlias, TypedDict, TypeVar, cast

import aiofiles
import aiohttp
from aiohttp import ClientTimeout
from aiolimiter import AsyncLimiter
from Crypto.Cipher import AES
from Crypto.Math.Numbers import Integer
from Crypto.PublicKey import RSA
from Crypto.Util import Counter

from cyberdrop_dl.clients.download_client import DownloadClient
from cyberdrop_dl.downloader.downloader import Downloader
from cyberdrop_dl.exceptions import CDLBaseError, DownloadError
from cyberdrop_dl.utils.logger import log

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping

    from aiohttp_client_cache.session import CachedSession
    from yarl import URL

    from cyberdrop_dl.data_structures.url_objects import MediaItem
    from cyberdrop_dl.managers.manager import Manager

T = TypeVar("T")
Array: TypeAlias = list[T] | tuple[T, ...]
U32Int: TypeAlias = int
U32IntArray: TypeAlias = Array[U32Int]
U32IntSequence: TypeAlias = Sequence[U32Int]
U32IntTupleArray: TypeAlias = tuple[U32Int, ...]
AnyDict: TypeAlias = dict[str, Any]


class MegaNzError(CDLBaseError):
    def __init__(self, msg: str | int, **kwargs) -> None:
        super().__init__(f"MegaNZ Error ({msg})", **kwargs)


ERROR_CODES = {
    -1: (
        "EINTERNAL",
        "An internal error has occurred. Please submit a bug report, detailing the exact circumstances in which this error occurred",
    ),
    -2: ("EARGS", "You have passed invalid arguments to this command"),
    -3: (
        "EAGAIN",
        "A temporary congestion or server malfunction prevented your request from being processed. No data was altered",
    ),
    -4: (
        "ERATELIMIT",
        "You have exceeded your command weight per time quota. Please wait a few seconds, then try again (this should never happen in sane real-life applications)",
    ),
    -5: ("EFAILED", "The upload failed. Please restart it from scratch"),
    -6: ("ETOOMANY", "Too many concurrent IP addresses are accessing this upload target URL"),
    -7: ("ERANGE", "The upload file packet is out of range or not starting and ending on a chunk boundary"),
    -8: ("EEXPIRED", "The upload target URL you are trying to access has expired. Please request a fresh one"),
    -9: ("ENOENT", "Object (typically, node or user) not found. Wrong password?"),
    -10: ("ECIRCULAR", "Circular linkage attempted"),
    -11: ("EACCESS", "Access violation (e.g., trying to write to a read-only share)"),
    -12: ("EEXIST", "Trying to create an object that already exists"),
    -13: ("EINCOMPLETE", "Trying to access an incomplete resource"),
    -14: ("EKEY", "A decryption operation failed (never returned by the API)"),
    -15: ("ESID", "Invalid or expired user session, please relogin"),
    -16: ("EBLOCKED", "User blocked"),
    -17: ("EOVERQUOTA", "Request over quota"),
    -18: ("ETEMPUNAVAIL", "Resource temporarily not available, please try again later"),
    -19: ("ETOOMANYCONNECTIONS", ""),
    -24: ("EGOINGOVERQUOTA", ""),
    -25: ("EROLLEDBACK", ""),
    -26: ("EMFAREQUIRED", "Multi-Factor Authentication Required"),
    -27: ("EMASTERONLY", ""),
    -28: ("EBUSINESSPASTDUE", ""),
    -29: ("EPAYWALL", "ODQ paywall state"),
    -400: ("ETOOERR", ""),
    -401: ("ESHAREROVERQUOTA", ""),
}


class RequestError(MegaNzError):
    """Error in API request."""

    def __init__(self, msg: str | int) -> None:
        self.code = code = msg if isinstance(msg, int) else None
        if code is not None:
            name, message = ERROR_CODES[code]
            ui_failure = f"{name}({code})"
        else:
            ui_failure = message = f"({msg})"
        super().__init__(ui_failure, message=message)


CHUNK_BLOCK_LEN = 16  # Hexadecimal
EMPTY_IV = b"\0" * CHUNK_BLOCK_LEN


class Chunk(NamedTuple):
    offset: int
    size: int


class Attributes(TypedDict):
    n: str  # name


class NodeType(IntEnum):
    DUMMY = -1
    FILE = 0
    FOLDER = 1
    ROOT_FOLDER = 2
    INBOX = 3
    TRASH = 4


class Node(TypedDict):
    t: NodeType  # type
    h: str  # id (aka handle)
    p: str  # parent id
    a: str  # attributes (within this: 'n' Name)
    k: str  # key
    u: str  # user id
    ts: int  # creation date (timestamp)
    g: NotRequired[str]  # Access URL

    #  Non standard properties, only used internally
    attributes: Attributes  # Decrypted attributes
    k_decrypted: U32IntTupleArray
    # full key, computed from value of `k` and the master key of the owner. This is the public access key
    key_decrypted: U32IntTupleArray


class FileOrFolder(Node):
    su: NotRequired[str]  # shared user id, only present in shared files / folder. The id of the owner
    sk: NotRequired[str]  # shared key. It's the base64 of `key_decrypted`

    #  Non standard properties, only used internally
    iv: U32IntTupleArray
    meta_mac: U32IntTupleArray
    sk_decrypted: U32IntTupleArray


class File(FileOrFolder):
    at: str  # File specific attributes (encrypted)
    fa: str  # File attributes


class Folder(FileOrFolder):
    f: list[FileOrFolder]  # Children (files or folders)
    ok: list[FileOrFolder]
    s: list[FileOrFolder]


SharedKey = dict[str, U32IntTupleArray]  # Mapping: (recipient) User Id ('u') -> decrypted value of shared key ('sk')
SharedkeysDict = dict[str, SharedKey]  # Mapping: (owner) Shared User Id ('su') -> SharedKey
FilesMapping = dict[str, FileOrFolder]  # key is parent_id ('p')


class DecryptData(NamedTuple):
    k: U32IntTupleArray
    iv: U32IntTupleArray
    meta_mac: U32IntTupleArray
    file_size: int = 0


def pad_bytes(data: bytes, length: int = CHUNK_BLOCK_LEN) -> bytes:
    """
    Pads a bytes-like object with null bytes to a multiple of the specified length.

    Args:
        data: The bytes-like object to pad (bytes or memoryview).
        length: The block size to pad to. Defaults to 16.

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

    def hash_buffer() -> bytes:
        return hashlib.sha256(buffer).digest()

    while True:
        digest = await asyncio.to_thread(hash_buffer)
        view = struct.unpack(">I", digest[:4])[0]  # big-endian uint32
        if view <= threshold:
            return f"1:{token_str}:{base64_url_encode(buffer[:4])}"

        # Increment the first 4 bytes as a little-endian integer
        for j in range(4):
            buffer[j] = (buffer[j] + 1) & 0xFF
            if buffer[j] != 0:
                break


def get_decrypt_data(node_type: NodeType, full_key: U32IntTupleArray) -> DecryptData:
    if node_type == NodeType.FILE:
        k = (full_key[0] ^ full_key[4], full_key[1] ^ full_key[5], full_key[2] ^ full_key[6], full_key[3] ^ full_key[7])
    else:
        k = full_key

    iv: U32IntTupleArray = (*full_key[4:6], 0, 0)
    meta_mac: U32IntTupleArray = full_key[6:8]
    return DecryptData(k, iv, meta_mac)


VALID_REQUEST_ID_CHARS = string.ascii_letters + string.digits


def _check_response_status(response: aiohttp.ClientResponse) -> None:
    if response.status > 0 and not (HTTPStatus.OK <= response.status < HTTPStatus.BAD_REQUEST):
        raise DownloadError(response.status)


class MegaApi:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.timeout = ClientTimeout(160)
        self.sid: str | None = None
        self.sequence_num: U32Int = random_u32int()
        self.request_id: str = "".join(random.choice(VALID_REQUEST_ID_CHARS) for _ in range(10))

        self.default_headers = {
            "Content-Type": "application/json",
            "User-Agent": manager.config_manager.global_settings_data.general.user_agent,
        }
        self.entrypoint = "https://g.api.mega.co.nz/cs"  # api still uses the old mega.co.nz domain
        self.logged_in = False
        self.root_id: str = ""
        self.inbox_id: str = ""
        self.trashbin_id: str = ""
        self._limiter = AsyncLimiter(100, 60)
        self._files = {}
        self.shared_keys: SharedkeysDict

    @property
    def session(self) -> CachedSession:
        return self.manager.client_manager._session

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

        async with self._limiter, self.session.disabled():
            response = await self.session.post(
                self.entrypoint, params=params, json=data, timeout=self.timeout, headers=self.default_headers
            )

        # Since around feb 2025, MEGA requires clients to solve a challenge during each login attempt.
        # When that happens, initial responses returns "402 Payment Required".
        # Challenge is inside the `X-Hashcash` header.
        # We need to solve the challenge and re-made the request with same params + the computed token
        # See:  https://github.com/gpailler/MegaApiClient/issues/248#issuecomment-2692361193

        if xhashcash_challenge := response.headers.get("X-Hashcash"):
            log("[MegaNZ] Solving xhashcash login challenge, this could take a few seconds...")
            xhashcash_token = await generate_hashcash_token(xhashcash_challenge)
            headers = self.default_headers | {"X-Hashcash": xhashcash_token}
            async with self._limiter, self.session.disabled():
                response = await self.session.post(
                    self.entrypoint, params=params, json=data, timeout=self.timeout, headers=headers
                )
        _check_response_status(response)
        if xhashcash_challenge := response.headers.get("X-Hashcash"):
            # Computed token failed
            msg = f"Login failed. Mega requested a proof of work with xhashcash: {xhashcash_challenge}"
            raise RequestError(msg)

        json_resp: list[Any] | list[int] | int = await response.json()

        def handle_int_resp(int_resp: int) -> Literal[0]:
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
            log("[MegaNZ] Logging as user [REDACTED]. This may take several seconds...")
            await self._login_user(email, password)
        else:
            log("[MegaNZ] Logging as anonymous temporary user. This may take several seconds...")
            await self.login_anonymous()
        _ = await self.get_files()  # This is to set the special folders id
        self.logged_in = True
        log("[MegaNZ] Login complete")
        return self

    def _process_login(self, resp: AnyDict, password: U32IntArray) -> None:
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

    def _process_node(self, file: Node) -> Node:
        """
        Processes a node and decrypts its metadata and attributes.

        Special nodes (root folder, inbox, trash bin) are identified and saved internally for reference

        This method is NOT thread safe. It modifies the internal state of the shared keys.
        """
        shared_keys: SharedkeysDict = self.shared_keys
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
                shared_keys.setdefault(file["su"], {})[file["h"]] = shared_key

            # shared files
            elif file["u"] and file["u"] in shared_keys:
                for hkey, shared_key in shared_keys[file["u"]].items():
                    if hkey in keys:
                        key = decrypt_key(base64_to_a32(keys[hkey]), shared_key)
                        break

            if file["h"] and file["h"] in shared_keys.get("EXP", {}):
                shared_key = shared_keys["EXP"][file["h"]]
                encrypted_key = str_to_a32(base64_url_decode(file["k"].split(":")[-1]))
                key = decrypt_key(encrypted_key, shared_key)
                file["sk_decrypted"] = shared_key

            if key is not None:
                crypto = get_decrypt_data(file["t"], key)
                file["k_decrypted"] = crypto.k
                file["iv"] = crypto.iv
                file["meta_mac"] = crypto.meta_mac
                file["key_decrypted"] = key
                attributes_bytes = base64_url_decode(file["a"])
                attributes = decrypt_attr(attributes_bytes, crypto.k)
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

        files = await self._get_nodes(lambda x: not bool(x.get("attributes")))
        return cast("FilesMapping", files)

    async def _get_nodes(self, predicate: Callable[[Node], bool] | None = None) -> dict[str, Node]:
        folder: Folder = await self.request({"a": "f", "c": 1, "r": 1})
        shared_keys: SharedkeysDict = {}
        self._init_shared_keys(folder, shared_keys)
        return await self._process_nodes(folder["f"], predicate=predicate)

    async def get_nodes_in_shared_folder(
        self, folder_id: str, shared_key: str | None = None
    ) -> dict[str, FileOrFolder]:
        folder: Folder = await self.request(
            {"a": "f", "c": 1, "ca": 1, "r": 1},
            {"n": folder_id},
        )

        return cast("dict[str, FileOrFolder]", await self._process_nodes(folder["f"], shared_key))

    async def _process_nodes(
        self,
        nodes: Sequence[Node],
        public_key: str | None = None,
        predicate: Callable[[Node], bool] | None = None,
    ) -> dict[str, Node]:
        """
        Processes multiple nodes at once, decrypting their metadata and attributes.

        If predicate is provided, only nodes for which `predicate(node)` returns `False` are included in the result.

        This method is NOT thread safe. It modifies the internal state of the shared keys.
        """
        # User may already have access to this folder (the key is saved in their account)
        folder_key = base64_to_a32(public_key) if public_key else None
        self.shared_keys.setdefault("EXP", {})

        async def process_nodes() -> dict[str, Node]:
            results = {}
            for index, node in enumerate(nodes):
                node_id = node["h"]
                if folder_key:
                    self.shared_keys["EXP"][node_id] = folder_key
                processed_node = self._process_node(node)
                if predicate is None or not predicate(processed_node):
                    results[node_id] = processed_node

                # We can compute this on another thread, so we sleep to avoid blocking the event loop for too long.
                if index % 500 == 0:
                    await asyncio.sleep(0)

            return results

        return await process_nodes()

    def _build_file_system(self, nodes_map: Mapping[str, Node], root_ids: list[str]) -> dict[Path, Node]:
        """Builds a flattened dictionary representing a file system from a list of items.

        Returns:
            A 1-level dictionary where the each keys is the full path to a file/folder, and each value is the actual file/folder
        """

        path_mapping: dict[Path, Node] = {}
        parents_mapping: dict[str, list[Node]] = {}

        for item in nodes_map.values():
            parent_id = item["p"]
            if parent_id not in parents_mapping:
                parents_mapping[parent_id] = []
            parents_mapping[parent_id].append(item)

        def build_tree(parent_id: str, current_path: Path) -> None:
            for item in parents_mapping.get(parent_id, []):
                item_path = current_path / item["attributes"]["n"]
                path_mapping[item_path] = item

                if item["t"] == NodeType.FOLDER:
                    build_tree(item["h"], item_path)

        for root_id in root_ids:
            root_item = nodes_map[root_id]
            name = root_item["attributes"]["n"]
            path = Path(name if name != "Cloud Drive" else ".")
            path_mapping[path] = root_item
            build_tree(root_id, path)

        sorted_mapping = dict(sorted(path_mapping.items()))
        return sorted_mapping

    async def build_file_system(self, nodes_map: Mapping[str, Node], root_ids: list[str]) -> dict[Path, Node]:
        return await asyncio.to_thread(self._build_file_system, nodes_map, root_ids)


class MegaDownloadClient(DownloadClient):
    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, manager.client_manager)
        self.decrypt_mapping: dict[URL, DecryptData] = {}

    async def _append_content(self, media_item: MediaItem, content: aiohttp.StreamReader) -> None:
        """Appends content to a file."""

        assert media_item.task_id is not None
        check_free_space = self.make_free_space_checker(media_item)
        check_download_speed = self.make_speed_checker(media_item)
        await check_free_space()
        await self._pre_download_check(media_item)

        crypto_data = self.decrypt_mapping[media_item.url]
        chunk_decryptor = MegaDecryptor(crypto_data)

        async with aiofiles.open(media_item.partial_file, mode="ab") as f:
            for _, chunk_size in get_chunks(crypto_data.file_size):
                await self.manager.states.RUNNING.wait()
                raw_chunk = await content.readexactly(chunk_size)
                chunk = chunk_decryptor.decrypt(raw_chunk)
                await check_free_space()
                chunk_size = len(chunk)
                await self.client_manager.speed_limiter.acquire(chunk_size)
                await f.write(chunk)
                self.manager.progress_manager.file_progress.advance_file(media_item.task_id, chunk_size)
                check_download_speed()

        self._post_download_check(media_item, content)
        chunk_decryptor.check_mac_integrity()

    def _pre_download_check(self, media_item: MediaItem) -> Coroutine[Any, Any, None]:
        def prepare() -> None:
            media_item.partial_file.parent.mkdir(parents=True, exist_ok=True)
            media_item.partial_file.unlink(missing_ok=True)  # We can't resume
            media_item.partial_file.touch()

        return asyncio.to_thread(prepare)


class MegaDownloader(Downloader):
    client: MegaDownloadClient

    def __init__(self, manager: Manager, domain: str) -> None:
        super().__init__(manager, domain)
        self.api = MegaApi(manager)

    @property
    def max_attempts(self):
        return 1

    def startup(self) -> None:
        """Starts the downloader."""
        self.client = MegaDownloadClient(self.manager)  # type: ignore[reportIncompatibleVariableOverride]
        self._semaphore = asyncio.Semaphore(self.manager.client_manager.get_download_slots(self.domain))

    def register(self, url: URL, crypto: DecryptData) -> None:
        self.client.decrypt_mapping[url] = crypto


class MegaDecryptor:
    def __init__(self, crypto: DecryptData) -> None:
        self.chunk_decryptor = _decrypt_chunks(crypto.k, crypto.iv, crypto.meta_mac)
        _ = next(self.chunk_decryptor)  # Prime chunk decryptor

    def decrypt(self, raw_chunk: bytes) -> bytes:
        return self.chunk_decryptor.send(raw_chunk)

    def check_mac_integrity(self) -> None:
        try:
            self.chunk_decryptor.send(None)  # type: ignore
        except StopIteration:
            pass


def _decrypt_chunks(
    k_decrypted: U32IntTupleArray, iv: U32IntTupleArray, meta_mac: U32IntTupleArray
) -> Generator[bytes, bytes, None]:
    """
    Decrypts chunks of data received via `send()` and yields the decrypted chunks.
    It decrypts chunks indefinitely until a sentinel value (`None`) is sent.

    NOTE: You MUST send `None` once after all chunks are processed to execute the MAC check.

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
