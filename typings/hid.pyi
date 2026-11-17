# Type stubs for the parts of hidapi (PyPI "hidapi", imported as "hid") that
# minidsp/transport.py uses. hidapi is a compiled Cython extension and ships no
# stubs of its own. The signatures follow hidapi 0.15.0: its docstrings and the
# definitions in its hid.pyx.

from collections.abc import Iterable
from typing import SupportsBytes, SupportsIndex, TypedDict

from _typeshed import ReadableBuffer

class _DeviceInfo(TypedDict):
    # The keys hidapi documents for enumerate(). Strings that are NULL in the C
    # library come back as "", never None.
    path: bytes
    vendor_id: int
    product_id: int
    serial_number: str
    release_number: int
    manufacturer_string: str
    product_string: str
    usage_page: int
    usage: int
    interface_number: int

def enumerate(vendor_id: int = 0, product_id: int = 0) -> list[_DeviceInfo]: ...

class device:
    # Raises OSError ("open failed") when the path cannot be opened.
    def open_path(self, path: bytes) -> None: ...
    # hidapi passes buff through bytes(), so it accepts whatever bytes() does;
    # returns hid_write()'s result (bytes written, -1 on error).
    def write(self, buff: Iterable[SupportsIndex] | SupportsIndex | SupportsBytes | ReadableBuffer) -> int: ...
    # Returns the bytes read as a list of ints; empty on timeout.
    def read(self, max_length: int, timeout_ms: int = 0) -> list[int]: ...
    def close(self) -> None: ...
