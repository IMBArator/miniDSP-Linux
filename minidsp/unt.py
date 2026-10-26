"""Read and write ``.unt`` preset files — the manufacturer editor's file format.

Layout (see ``analysis/protocol.md``, "Configuration File Format (.unt)"):

```text
0x000    50 B   header: 16-byte magic + the 34-byte 0x19 header block
0x032   432 B   slot U01: slot byte + 429-byte preset blob + CRLF
  ...
0x3112  432 B   slot U30
```

Unused slots are 432 bytes of ``0x64`` filler. :class:`UntFile` keeps the
whole file as one buffer and edits fields in place, so bytes it does not
model survive a load → save unchanged (ADR-0025). Device transfer lives in
:meth:`minidsp.device.DSPmini.export_unt` / :meth:`~minidsp.device.DSPmini.restore_unt`.
"""

from __future__ import annotations

import os
from pathlib import Path

from .protocol import (
    DEVICE_HEADER_SIZE,
    OP_DEVICE_HEADER,
    pack_preset_params,
    parse_device_header,
    parse_preset_params,
)

UNT_MAGIC = b"***4x4MINIV010**"
UNT_SIZE = 13010
UNT_HEADER_SIZE = 50
UNT_SLOT_COUNT = 30
UNT_SLOT_BASE = 0x32
UNT_SLOT_STRIDE = 432
UNT_BLOB_SIZE = 429        # first 429 bytes of the 450-byte device config
UNT_EMPTY_FILL = 0x64      # every byte of an unused slot
UNT_ACTIVE_SLOT_OFFSET = 0x11
UNT_PIN_OFFSET = 0x1D      # 4 ASCII chars, 0x1D–0x20
EMPTY_PRESET_NAME = "Default Preset"   # 0x29 name of a never-stored slot

_HEADER_BLOCK_OFFSET = 0x10            # header 0x10–0x31 = the 34-byte 0x19 block
_PRESET_NAME = slice(2, 16)            # within a slot blob, after the FF FF marker
_CRLF = b"\r\n"

# Header block of a blank file, as in the editor-made blank template: device 1,
# active U01, 30 slots, "0000", counter 0x270F, PIN "1234", version 10.
_BLANK_HEADER_BLOCK = (bytes.fromhex("01011e") + b"0000" + bytes.fromhex("0000270f0000")
                       + b"1234" + bytes.fromhex("000a00") + b"4x4D Amplifier")


class UntParseError(ValueError):
    """Raised when bytes are not a valid ``.unt`` file."""


def _check_slot(slot: int) -> None:
    if not 1 <= slot <= UNT_SLOT_COUNT:
        raise ValueError(f"slot must be 1–{UNT_SLOT_COUNT} (U01–U30), got {slot}")


def slots_to_save(preset_names: list[str]) -> list[int]:
    """Return the slots the editor writes to a ``.unt`` file.

    The editor saves every slot whose ``0x29`` name is not ``"Default Preset"``
    (verified with three editor-saved files). Empty names — e.g. a failed name
    read — are skipped as well.

    Args:
        preset_names: The 30 names in slot order (index 0 = U01), as returned
            by :meth:`minidsp.device.DSPmini.read_preset_names`.

    Returns:
        1-based slot numbers in ascending order.
    """
    return [i + 1 for i, name in enumerate(preset_names[:UNT_SLOT_COUNT])
            if name.strip() and name.strip() != EMPTY_PRESET_NAME]


class UntFile:
    """A ``.unt`` file held as its raw 13010 bytes.

    Args:
        data: The complete file contents.

    Raises:
        UntParseError: If the size, magic or active-slot byte is invalid.
    """

    def __init__(self, data: bytes | bytearray) -> None:
        if len(data) != UNT_SIZE:
            raise UntParseError(f"expected {UNT_SIZE} bytes, got {len(data)}")
        if bytes(data[:len(UNT_MAGIC)]) != UNT_MAGIC:
            raise UntParseError(f"bad magic {bytes(data[:len(UNT_MAGIC)])!r}")
        # 1–30 in every editor file; 0 is accepted for an active F00
        if data[UNT_ACTIVE_SLOT_OFFSET] > UNT_SLOT_COUNT:
            raise UntParseError(f"active slot byte {data[UNT_ACTIVE_SLOT_OFFSET]} out of range")
        self._data = bytearray(data)

    # --- construction ---------------------------------------------------

    @classmethod
    def read(cls, path: str | Path) -> UntFile:
        """Load a ``.unt`` file from disk.

        Raises:
            UntParseError: If the file is not a valid ``.unt``.
        """
        return cls(Path(path).read_bytes())

    @classmethod
    def from_header_block(cls, block: bytes) -> UntFile:
        """Build a file with all slots empty around a 34-byte header block.

        Args:
            block: Header bytes 0x10–0x31, e.g. the ``'raw'`` value of
                :func:`~minidsp.protocol.parse_device_header`.

        Raises:
            ValueError: If ``block`` is not 34 bytes.
        """
        if len(block) != DEVICE_HEADER_SIZE:
            raise ValueError(f"header block must be {DEVICE_HEADER_SIZE} bytes, got {len(block)}")
        data = bytearray([UNT_EMPTY_FILL]) * UNT_SIZE
        data[:len(UNT_MAGIC)] = UNT_MAGIC
        data[_HEADER_BLOCK_OFFSET:UNT_HEADER_SIZE] = block
        return cls(data)

    @classmethod
    def blank(cls) -> UntFile:
        """Return an empty file (active U01, PIN ``"1234"``, all slots unused)."""
        return cls.from_header_block(_BLANK_HEADER_BLOCK)

    # --- header ---------------------------------------------------------

    @property
    def header_block(self) -> bytes:
        """The 34 header bytes 0x10–0x31 (same layout as the 0x19 reply)."""
        return bytes(self._data[_HEADER_BLOCK_OFFSET:UNT_HEADER_SIZE])

    @property
    def header(self) -> dict:
        """Parsed header fields, see :func:`~minidsp.protocol.parse_device_header`."""
        return parse_device_header(bytes([OP_DEVICE_HEADER]) + self.header_block)

    @property
    def active_slot(self) -> int:
        """Active preset slot (1=U01 … 30=U30)."""
        return self._data[UNT_ACTIVE_SLOT_OFFSET]

    @active_slot.setter
    def active_slot(self, slot: int) -> None:
        _check_slot(slot)
        self._data[UNT_ACTIVE_SLOT_OFFSET] = slot

    @property
    def pin(self) -> str:
        """The 4-character lock PIN field."""
        return self._data[UNT_PIN_OFFSET:UNT_PIN_OFFSET + 4].decode("ascii", errors="replace")

    @pin.setter
    def pin(self, pin: str) -> None:
        encoded = pin.encode("ascii")
        if len(encoded) != 4:
            raise ValueError(f"PIN must be 4 ASCII characters, got {pin!r}")
        self._data[UNT_PIN_OFFSET:UNT_PIN_OFFSET + 4] = encoded

    # --- slots ----------------------------------------------------------

    def _slot_offset(self, slot: int) -> int:
        _check_slot(slot)
        return UNT_SLOT_BASE + (slot - 1) * UNT_SLOT_STRIDE

    def is_filled(self, slot: int) -> bool:
        """``True`` if the slot holds a preset (is not ``0x64`` filler)."""
        return self._data[self._slot_offset(slot)] != UNT_EMPTY_FILL

    def filled_slots(self) -> list[int]:
        """1-based numbers of all slots that hold a preset."""
        return [s for s in range(1, UNT_SLOT_COUNT + 1) if self.is_filled(s)]

    def slot_blob(self, slot: int) -> bytes | None:
        """The 429-byte preset blob of a slot, or ``None`` if it is unused."""
        if not self.is_filled(slot):
            return None
        off = self._slot_offset(slot) + 1
        return bytes(self._data[off:off + UNT_BLOB_SIZE])

    def set_slot_blob(self, slot: int, blob: bytes) -> None:
        """Store a preset blob in a slot (slot byte + blob + CRLF).

        Args:
            slot: 1–30.
            blob: The 429-byte ``.unt`` blob, or a longer device config (450
                bytes from 0x27/0x28 reads) of which the first 429 are stored.

        Raises:
            ValueError: If ``blob`` is shorter than 429 bytes.
        """
        if len(blob) < UNT_BLOB_SIZE:
            raise ValueError(f"preset blob must be at least {UNT_BLOB_SIZE} bytes, got {len(blob)}")
        off = self._slot_offset(slot)
        self._data[off] = slot
        self._data[off + 1:off + 1 + UNT_BLOB_SIZE] = blob[:UNT_BLOB_SIZE]
        self._data[off + 1 + UNT_BLOB_SIZE:off + UNT_SLOT_STRIDE] = _CRLF

    def clear_slot(self, slot: int) -> None:
        """Mark a slot unused (432 bytes of ``0x64`` filler)."""
        off = self._slot_offset(slot)
        self._data[off:off + UNT_SLOT_STRIDE] = bytes([UNT_EMPTY_FILL]) * UNT_SLOT_STRIDE

    def slot_name(self, slot: int) -> str | None:
        """The preset name of a slot (trailing spaces stripped), or ``None``."""
        blob = self.slot_blob(slot)
        if blob is None:
            return None
        return blob[_PRESET_NAME].decode("ascii", errors="replace").rstrip(" \x00")

    def slot_params(self, slot: int) -> dict | None:
        """Parsed parameters of a slot (:func:`~minidsp.protocol.parse_preset_params`)."""
        blob = self.slot_blob(slot)
        return parse_preset_params(blob) if blob is not None else None

    def set_slot_params(self, slot: int, params: dict, name: str | None = None,
                        base: bytes | None = None) -> None:
        """Write preset parameters into a slot, keeping all unmodelled bytes.

        Args:
            slot: 1–30.
            params: Dict in the shape of :func:`~minidsp.protocol.parse_preset_params`.
            name: New preset name (max 14 ASCII chars); ``None`` keeps the
                current one.
            base: Blob to patch when the slot is unused. Defaults to an
                ``FF FF`` marker, a space name and zero bytes elsewhere.
        """
        blob = self.slot_blob(slot)
        if blob is None:
            blob = base[:UNT_BLOB_SIZE] if base is not None else (
                b"\xff\xff" + b" " * 14 + bytes(UNT_BLOB_SIZE - 16))
        blob = bytearray(pack_preset_params(params, blob))
        if name is not None:
            blob[_PRESET_NAME] = name[:14].encode("ascii", errors="replace").ljust(14, b" ")
        self.set_slot_blob(slot, bytes(blob))

    # --- output ---------------------------------------------------------

    def to_bytes(self) -> bytes:
        """The complete 13010-byte file."""
        return bytes(self._data)

    def write(self, path: str | Path) -> None:
        """Write the file atomically.

        The bytes go to a temporary file next to ``path``, are flushed to
        disk and then renamed over the destination, so an interrupted write
        leaves an existing file untouched.
        """
        target = Path(path)
        tmp = target.with_name(f".{target.name}.tmp")
        try:
            with open(tmp, "wb") as fh:
                fh.write(self.to_bytes())
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, target)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
