"""Drop-in ``ooz.decompress(src, out_len)`` backed by a local decoder.

The palooz python extension does not build on this machine (its compressor half
fails to compile against the current libc++).  Prefer the small ``eqsav``
binding when it is installed; otherwise use the decompressor-only
``libooz.dylib`` beside this module through :mod:`oozshim`.  Both paths assert
the exact output length.
"""
try:
    from eqsav import ooz_decompress as _d
except ModuleNotFoundError:
    from oozshim import kraken as _d


def decompress(src, out_len):
    return _d(bytes(src), int(out_len))
