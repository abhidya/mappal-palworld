"""Minimal Oodle-Kraken decompressor for this world's Level.sav files.

Palworld saves here carry magic b'PlM' (not the b'PlZ' palworld_save_tools
knows) and their payload is Oodle-compressed, not zlib. libooz.dylib is
zao/ooz built decompression-only from source (see ooz_zao/); Ooz_Decompress
is the same public entry point CUE4Parse and the `ooz` python module use.

decompress_sav(raw) -> gvas bytes.  Handles both PlM (Oodle) and PlZ
(zlib / double-zlib) containers, so it is a drop-in for either save version.
"""
import ctypes, os, zlib

_LIB = ctypes.CDLL(os.path.join(os.path.dirname(os.path.abspath(__file__)), "libooz.dylib"))
_LIB.Ooz_Decompress.argtypes = [ctypes.c_char_p, ctypes.c_size_t,
                                   ctypes.c_char_p, ctypes.c_size_t]
_LIB.Ooz_Decompress.restype = ctypes.c_int

SAFE_SPACE = 64


def kraken(src: bytes, out_len: int) -> bytes:
    dst = ctypes.create_string_buffer(out_len + SAFE_SPACE)
    n = _LIB.Ooz_Decompress(src, len(src), dst, out_len)
    if n != out_len:
        raise ValueError(f"Ooz_Decompress returned {n}, expected {out_len}")
    return dst.raw[:out_len]


def decompress_sav(data: bytes) -> bytes:
    off = 12
    ulen = int.from_bytes(data[0:4], "little")
    clen = int.from_bytes(data[4:8], "little")
    magic = data[8:11]
    stype = data[11]
    if magic == b"CNK":
        ulen = int.from_bytes(data[12:16], "little")
        clen = int.from_bytes(data[16:20], "little")
        magic = data[20:23]
        stype = data[23]
        off = 24
    if magic not in (b"PlM", b"PlZ"):
        raise ValueError(f"not a Palworld save: magic {magic!r}")
    body = data[off:off + clen]
    if magic == b"PlM":
        out = kraken(body, ulen)
        if stype == 0x32:            # doubly compressed
            out = kraken(out, int.from_bytes(out[0:4], "little"))
        return out
    if stype == 0x31:
        return zlib.decompress(zlib.decompress(body))
    return zlib.decompress(body)
