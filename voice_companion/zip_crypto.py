"""Password-protected zip files (Will, November 4, 2026).

Reading: the older "ZipCrypto" kind is read by Python's zipfile. The strong kind, WinZip AES
(what 7-Zip and WinRAR make), is read here.

Writing: Alt+Shift+Z makes a WinZip AES-256 zip (AE-2), the strong kind Will chose. Windows'
own File Explorer cannot open it; 7-Zip, WinRAR and Voice Companion can.

WinZip AES, as published by WinZip ("AES Encryption Information"):
- Each file's extra field 0x9901 holds the vendor version (AE-1 or AE-2), the key strength
  (1, 2 or 3 for AES-128, 192 or 256) and the real compression method. The compression method in
  the header is 99.
- The file data is: salt (8, 12 or 16 bytes), a 2-byte password check, the encrypted data, and a
  10-byte authentication code.
- Keys come from PBKDF2-HMAC-SHA1 with 1000 rounds: the AES key, then the HMAC key, then the
  2-byte check. AES runs in counter mode with a little-endian counter that starts at 1.
- The authentication code is the first 10 bytes of HMAC-SHA1 over the encrypted data.
"""
import hashlib
import hmac
import os
import struct
import time
import zipfile
import zlib

AES_METHOD = 99
AES_EXTRA = 0x9901
STRENGTHS = {1: 16, 2: 24, 3: 32}      # key bytes
SALTS = {1: 8, 2: 12, 3: 16}
ROUNDS = 1000
CHUNK = 1024 * 1024


class WrongPassword(ValueError):
    pass


class AesCounter:
    """AES in WinZip's counter mode: a 16-byte little-endian counter starting at 1."""
    def __init__(self, key):
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        self.encrypt_block = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
        self.counter = 1
        self.spare = b''

    def apply(self, data):
        need = len(data) - len(self.spare)
        stream = self.spare
        if need > 0:
            blocks = (need + 15) // 16
            counters = b''.join((self.counter + i).to_bytes(16, 'little') for i in range(blocks))
            self.counter += blocks
            stream += self.encrypt_block.update(counters)
        self.spare = stream[len(data):]
        return bytes(a ^ b for a, b in zip(data, stream)) if len(data) < 64 else _xor(data, stream)


def _xor(data, stream):
    size = len(data)
    return (int.from_bytes(data, 'little') ^ int.from_bytes(stream[:size], 'little')).to_bytes(size, 'little')


def keys(password, salt, strength):
    size = STRENGTHS[strength]
    material = hashlib.pbkdf2_hmac('sha1', password.encode('utf-8'), salt, ROUNDS, 2 * size + 2)
    return material[:size], material[size:2 * size], material[2 * size:]


def aes_details(info):
    """(strength, real compression method) from a member's 0x9901 extra field, or None."""
    extra = info.extra
    at = 0
    while at + 4 <= len(extra):
        kind, size = struct.unpack('<HH', extra[at:at + 4])
        if kind == AES_EXTRA and size >= 7:
            _version, vendor, strength, method = struct.unpack('<H2sBH', extra[at + 4:at + 11])
            if vendor == b'AE' and strength in STRENGTHS:
                return strength, method
        at += 4 + size
    return None


def is_aes(info):
    return info.compress_type == AES_METHOD and aes_details(info) is not None


def _data_start(handle, info):
    handle.seek(info.header_offset)
    header = handle.read(30)
    if header[:4] != b'PK\x03\x04':
        raise zipfile.BadZipFile('damaged')
    name_size, extra_size = struct.unpack('<HH', header[26:30])
    return info.header_offset + 30 + name_size + extra_size


def read_aes(path, info, password, output):
    """Decrypt one WinZip AES member of the zip at path into the open file output."""
    strength, method = aes_details(info)
    salt_size = SALTS[strength]
    with open(path, 'rb') as handle:
        start = _data_start(handle, info)
        handle.seek(start)
        salt = handle.read(salt_size)
        check = handle.read(2)
        aes_key, mac_key, expected = keys(password, salt, strength)
        if not hmac.compare_digest(check, expected):
            raise WrongPassword('wrong password')
        remaining = info.compress_size - salt_size - 2 - 10
        if remaining < 0:
            raise zipfile.BadZipFile('damaged')
        counter = AesCounter(aes_key)
        mac = hmac.new(mac_key, digestmod=hashlib.sha1)
        inflate = zlib.decompressobj(-15) if method == 8 else None
        if method not in (0, 8):
            raise ValueError('This zip uses a kind of compression Voice Companion cannot read.')
        while remaining:
            block = handle.read(min(CHUNK, remaining))
            if not block:
                raise zipfile.BadZipFile('damaged')
            remaining -= len(block)
            mac.update(block)
            plain = counter.apply(block)
            output.write(inflate.decompress(plain) if inflate else plain)
        if inflate:
            output.write(inflate.flush())
        if not hmac.compare_digest(handle.read(10), mac.digest()[:10]):
            raise zipfile.BadZipFile('damaged')


# Writing ----------------------------------------------------------------------------------
def _dos_time(stamp):
    moment = time.localtime(stamp)
    year = max(1980, moment.tm_year)
    return (((moment.tm_hour << 11) | (moment.tm_min << 5) | (moment.tm_sec // 2)),
            (((year - 1980) << 9) | (moment.tm_mon << 5) | moment.tm_mday))


def write_aes_zip(entries, target, password):
    """Write a new WinZip AES-256 (AE-2) zip at target. entries: (file path or None, name in zip)
    pairs, None for an empty folder. Returns how many files went in. Refuses zips of 4 GB or more."""
    if not password:
        raise ValueError('Type a password for the zip file.')
    central = []
    count = 0
    with open(target, 'xb') as out:
        for file, name in entries:
            encoded = name.encode('utf-8')
            if file is None:
                stamp = time.time()
                header_offset = out.tell()
                clock, day = _dos_time(stamp)
                out.write(struct.pack('<4s5H3L2H', b'PK\x03\x04', 20, 0x800, 0, clock, day, 0, 0, 0, len(encoded), 0) + encoded)
                central.append((encoded, b'', 0, 0, 0, 0, clock, day, header_offset, 0x10))
                continue
            stamp = os.stat(file).st_mtime
            clock, day = _dos_time(stamp)
            extra = struct.pack('<HHH2sBH', AES_EXTRA, 7, 2, b'AE', 3, 8)
            header_offset = out.tell()
            out.write(struct.pack('<4s5H3L2H', b'PK\x03\x04', 51, 0x801, AES_METHOD, clock, day, 0, 0, 0, len(encoded), len(extra)) + encoded + extra)
            salt = os.urandom(16)
            aes_key, mac_key, check = keys(password, salt, 3)
            out.write(salt + check)
            counter = AesCounter(aes_key)
            mac = hmac.new(mac_key, digestmod=hashlib.sha1)
            deflate = zlib.compressobj(6, zlib.DEFLATED, -15)
            packed = 0
            size = 0
            with open(file, 'rb') as source:
                while True:
                    block = source.read(CHUNK)
                    if not block:
                        break
                    size += len(block)
                    secret = counter.apply(deflate.compress(block))
                    mac.update(secret); out.write(secret); packed += len(secret)
                tail = counter.apply(deflate.flush())
                mac.update(tail); out.write(tail); packed += len(tail)
            out.write(mac.digest()[:10])
            compressed = 16 + 2 + packed + 10
            if compressed >= 0xFFFFFFFF or size >= 0xFFFFFFFF or out.tell() >= 0xFFFFFFFF:
                raise ValueError('A password zip must be smaller than 4 GB. Zip fewer items.')
            end = out.tell()
            out.seek(header_offset + 18)
            out.write(struct.pack('<LL', compressed, size))   # AE-2: the CRC stays 0
            out.seek(end)
            central.append((encoded, extra, AES_METHOD, 0x801, compressed, size, clock, day, header_offset, 0x20))
            count += 1
        start = out.tell()
        for encoded, extra, method, flags, compressed, size, clock, day, offset, attributes in central:
            out.write(struct.pack('<4s6H3L5H2L', b'PK\x01\x02', 51, 51 if method else 20, flags if method else 0x800, method,
                                  clock, day, 0, compressed, size, len(encoded), len(extra), 0, 0, 0, attributes, offset)
                      + encoded + extra)
        length = out.tell() - start
        out.write(struct.pack('<4s4H2LH', b'PK\x05\x06', 0, 0, len(central), len(central), length, start, 0))
    return count
