"""Drop-in `ooz.decompress(src, out_len)` backed by libooz_dec.dylib.

The palooz python extension does not build on this machine (its compressor half
fails to compile against the current libc++), so only the ooz DECOMPRESSOR
translation units were built into libooz_dec.dylib and are called via ctypes.
Output length is asserted exactly, same check palooz makes.
"""
from eqsav import ooz_decompress as _d


def decompress(src, out_len):
    return _d(bytes(src), int(out_len))
