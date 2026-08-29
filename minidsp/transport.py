"""HID transport layer for the t.racks DSP 4x4 Mini.

The DSP is reachable over different HID stacks depending on the operating
system. This module hides that behind :class:`Transport` — a byte-level pipe
that knows how to find the device, open it exclusively, and move 64-byte
reports in both directions. Everything protocol-related (framing, retries,
command semantics) lives in :mod:`minidsp.protocol` and
:mod:`minidsp.device`; the transport only moves bytes.

Implementations:
    :class:`HidrawTransport`: Linux — the kernel ``/dev/hidrawN`` node opened
        with plain ``os.open``/``os.read``/``os.write``, serialised with
        ``fcntl.flock`` and timed out with ``select``. No third-party
        dependency.
    :class:`HidapiTransport`: Windows — ``hidapi`` (PyPI ``hidapi``, imported
        as ``hid``), serialised with a named Win32 mutex. Installed
        automatically on Windows via a platform-marker dependency.

Use :func:`default_transport` to get the right one for the running platform.
"""

from __future__ import annotations

import abc
import glob
import logging
import os
import sys

from .protocol import PRODUCT_ID, REPORT_SIZE, VENDOR_ID

if sys.platform != "win32":
    import fcntl
    import select

log = logging.getLogger(__name__)


class DeviceClosedError(OSError):
    """Raised when an I/O method is called on a closed :class:`DSPmini` handle.

    Subclasses :class:`OSError` so existing ``except OSError`` blocks in
    callers catch it transparently — useful when device disappearance
    (cable yank) and ordinary "you forgot to call ``open()``" should be
    handled the same way.
    """


class Transport(abc.ABC):
    """Byte-level HID pipe to the DSP.

    A transport is responsible for locating the device, opening it with a
    single-instance guard, and exchanging raw 64-byte HID reports. It knows
    nothing about frame structure, opcodes, or retries.
    """

    @staticmethod
    @abc.abstractmethod
    def find_device() -> str | None:
        """Locate the DSP on this system.

        Returns:
            An opaque, transport-specific device path (a ``/dev/hidrawN``
            node on Linux, a HID interface path on Windows), or ``None`` if
            the device is not connected.
        """

    @abc.abstractmethod
    def open(self, device_path: str | None = None) -> None:
        """Open the device and acquire the single-instance guard.

        Args:
            device_path: Transport-specific device path. If ``None``, the
                device is auto-detected via :meth:`find_device`.

        Raises:
            OSError: If the device is not found or is already in use by
                another process.
        """

    @abc.abstractmethod
    def close(self) -> None:
        """Close the device and release the single-instance guard.

        Calling this on an already-closed transport is a no-op.
        """

    @abc.abstractmethod
    def write(self, report: bytes) -> None:
        """Write one 64-byte HID OUT report.

        Args:
            report: Exactly :data:`~minidsp.protocol.REPORT_SIZE` bytes.

        Raises:
            DeviceClosedError: If the transport is not open.
        """

    @abc.abstractmethod
    def read(self, timeout_ms: int = 500) -> bytes | None:
        """Read one 64-byte HID IN report.

        Args:
            timeout_ms: Read timeout in milliseconds.

        Returns:
            Raw report bytes, or ``None`` on timeout or empty read.

        Raises:
            DeviceClosedError: If the transport is not open.
        """

    @property
    @abc.abstractmethod
    def is_open(self) -> bool:
        """Whether the device is currently open."""


class HidrawTransport(Transport):
    """Linux transport over the kernel's ``/dev/hidrawN`` character device.

    Acquires an **exclusive advisory lock** (``fcntl.flock(LOCK_EX|LOCK_NB)``)
    on the hidraw file descriptor in :meth:`open`, so a second process (or a
    second instance in the same process) cannot open the device concurrently.
    The lock is released by the kernel when the fd is closed — including on
    crash, so there is no stale lock to clean up.

    Note:
        ``fcntl`` locks are advisory — they protect against other cooperative
        processes but do not prevent a raw ``open()`` by uncooperative
        programs (e.g. the manufacturer Windows app under Wine).
    """

    def __init__(self) -> None:
        self._fd: int | None = None

    @staticmethod
    def find_device() -> str | None:
        """Find the ``/dev/hidrawN`` path for the DSPmini by scanning sysfs for VID/PID.

        Returns:
            Path string such as ``"/dev/hidraw0"``, or ``None`` if the device is
            not connected or not yet visible in sysfs.
        """
        for path in sorted(glob.glob("/sys/class/hidraw/hidraw*/device")):
            uevent_path = os.path.join(path, "uevent")
            try:
                with open(uevent_path) as f:
                    uevent = f.read()
            except OSError:
                continue
            # Look for HID_ID=0003:00000168:00000821 (bus_type:vid:pid)
            vid_str = f"{VENDOR_ID:08X}"
            pid_str = f"{PRODUCT_ID:08X}"
            if vid_str in uevent and pid_str in uevent:
                hidraw_name = path.split("/")[-2]  # e.g. "hidraw0"
                return f"/dev/{hidraw_name}"
        return None

    def open(self, device_path: str | None = None) -> None:
        """Open the hidraw node with ``O_RDWR`` and take the exclusive lock.

        If the lock cannot be acquired the fd is closed again and an
        ``OSError`` is raised — the caller does not need to call
        :meth:`close` in that case.

        Args:
            device_path: Path to the hidraw device (e.g. ``"/dev/hidraw0"``).
                If ``None``, auto-detects via sysfs VID/PID matching.

        Raises:
            OSError: If the device is not found or the exclusive lock cannot
                be acquired (already held by another process).
        """
        if device_path is None:
            device_path = self.find_device()
            if device_path is None:
                raise OSError(
                    "DSP 4x4 Mini not found. Is it connected? "
                    "Check: lsusb | grep 0168"
                )
        self._fd = os.open(device_path, os.O_RDWR)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            os.close(self._fd)
            self._fd = None
            raise OSError(
                f"{device_path} is already in use by another process"
            )
        log.info("Opened %s (exclusive lock acquired)", device_path)

    def close(self) -> None:
        """Close the fd, which releases the exclusive lock."""
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def write(self, report: bytes) -> None:
        """Write a 64-byte HID OUT report to the hidraw node."""
        if self._fd is None:
            raise DeviceClosedError("Device not open")
        os.write(self._fd, report)

    def read(self, timeout_ms: int = 500) -> bytes | None:
        """Wait up to ``timeout_ms`` for a HID IN report and read it.

        Args:
            timeout_ms: Read timeout in milliseconds.

        Returns:
            Raw report bytes, or ``None`` on timeout or empty read.
        """
        if self._fd is None:
            raise DeviceClosedError("Device not open")
        timeout_s = timeout_ms / 1000.0
        r, _, _ = select.select([self._fd], [], [], timeout_s)
        if not r:
            log.debug("RX timeout (%d ms)", timeout_ms)
            return None
        data = os.read(self._fd, REPORT_SIZE)
        if not data:
            log.debug("RX empty read")
            return None
        return bytes(data)

    @property
    def is_open(self) -> bool:
        """Whether the hidraw fd is currently open."""
        return self._fd is not None


class HidapiTransport(Transport):
    """Windows transport over ``hidapi`` (PyPI ``hidapi``, imported as ``hid``).

    Windows has no hidraw node and no ``flock``, so this implementation
    differs from :class:`HidrawTransport` in two places, both contained here:

    * **Report ID** — the DSP uses unnumbered reports, so every write is
      prefixed with a ``0x00`` report number (65 bytes on the wire) and reads
      return the bare 64 data bytes. Frames built by
      :mod:`minidsp.protocol` are unchanged.
    * **Single-instance guard** — a named Win32 mutex
      (:data:`MUTEX_NAME`) replaces the flock. Windows abandons the mutex
      when the owning process dies, so like flock there is no stale lock to
      clean up. The ``Local\\`` namespace scopes it to the current login
      session: two sessions on the same machine are not guarded against each
      other.

    ``hid`` is imported lazily inside the methods, so importing this module
    never requires hidapi on platforms that do not use it.
    """

    #: Name of the single-instance mutex, session-local and VID/PID-specific.
    MUTEX_NAME = "Local\\minidsp-hid-0168-0821"

    #: Win32 ``ERROR_ALREADY_EXISTS`` — another process already holds the mutex.
    _ERROR_ALREADY_EXISTS = 183

    def __init__(self) -> None:
        self._dev = None
        self._mutex: int | None = None

    @staticmethod
    def find_device() -> str | None:
        """Find the DSP's HID interface path via ``hid.enumerate``.

        All matching entries are debug-logged (a device may expose several
        HID collections) and the first one is used.

        Returns:
            The HID interface path as a string, or ``None`` if no interface
            with the DSP's VID/PID is present.
        """
        import hid

        entries = hid.enumerate(VENDOR_ID, PRODUCT_ID)
        for entry in entries:
            log.debug(
                "hidapi enumerate: path=%r interface=%s usage_page=0x%04x usage=0x%04x",
                entry.get("path"),
                entry.get("interface_number"),
                entry.get("usage_page", 0),
                entry.get("usage", 0),
            )
        if not entries:
            return None
        path = entries[0].get("path")
        if path is None:
            return None
        return path.decode("utf-8", errors="replace") if isinstance(path, bytes) else path

    def open(self, device_path: str | None = None) -> None:
        """Take the named mutex and open the HID interface.

        Args:
            device_path: HID interface path as returned by
                :meth:`find_device`. If ``None``, the device is auto-detected
                by VID/PID.

        Raises:
            OSError: If the device is not found, another process already
                holds the single-instance mutex, or hidapi cannot open the
                interface.
        """
        import hid

        if device_path is None:
            device_path = self.find_device()
            if device_path is None:
                raise OSError(
                    "DSP 4x4 Mini not found. Is it connected? "
                    "Check Device Manager for a HID device with VID 0168 / PID 0821"
                )
        self._acquire_mutex(device_path)
        try:
            dev = hid.device()
            dev.open_path(device_path.encode("utf-8"))
        except Exception:
            self._release_mutex()
            raise
        self._dev = dev
        log.info("Opened %s (single-instance mutex acquired)", device_path)

    def close(self) -> None:
        """Close the HID interface and release the named mutex."""
        if self._dev is not None:
            self._dev.close()
            self._dev = None
        self._release_mutex()

    def write(self, report: bytes) -> None:
        """Write a HID OUT report, prefixed with report number ``0x00``.

        Args:
            report: The 64 data bytes; 65 bytes go on the wire.
        """
        if self._dev is None:
            raise DeviceClosedError("Device not open")
        self._dev.write(b"\x00" + report)

    def read(self, timeout_ms: int = 500) -> bytes | None:
        """Read a HID IN report in blocking mode with a timeout.

        Args:
            timeout_ms: Read timeout in milliseconds. hidapi is kept in
                blocking mode and given the timeout per call, so the existing
                per-command timeouts apply unchanged.

        Returns:
            The report's data bytes, or ``None`` on timeout (hidapi returns
            an empty list) — never the report number, which hidapi strips
            for unnumbered reports.
        """
        if self._dev is None:
            raise DeviceClosedError("Device not open")
        data = self._dev.read(REPORT_SIZE, timeout_ms=timeout_ms)
        if not data:
            log.debug("RX timeout (%d ms)", timeout_ms)
            return None
        if len(data) != REPORT_SIZE:
            log.debug("RX unexpected report length (%d bytes, expected %d)",
                      len(data), REPORT_SIZE)
        return bytes(data)

    @property
    def is_open(self) -> bool:
        """Whether the HID interface is currently open."""
        return self._dev is not None

    # --- Single-instance guard ---

    def _acquire_mutex(self, device_path: str) -> None:
        """Create the named mutex, failing if another process owns it.

        Args:
            device_path: Only used for the error message.

        Raises:
            OSError: If the mutex already exists (another process is talking
                to the device) or cannot be created.
        """
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        handle = kernel32.CreateMutexW(None, True, self.MUTEX_NAME)
        err = ctypes.get_last_error()
        if not handle:
            raise OSError(f"Could not create single-instance mutex (error {err})")
        if err == self._ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
            raise OSError(
                f"{device_path} is already in use by another process"
            )
        self._mutex = handle

    def _release_mutex(self) -> None:
        """Release and close the named mutex if it is held."""
        if self._mutex is None:
            return
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = ctypes.c_void_p(self._mutex)
        kernel32.ReleaseMutex(handle)
        kernel32.CloseHandle(handle)
        self._mutex = None


def default_transport() -> Transport:
    """Return the transport implementation for the running platform.

    Returns:
        A :class:`HidapiTransport` on Windows, a :class:`HidrawTransport`
        everywhere else.
    """
    if sys.platform == "win32":
        return HidapiTransport()
    return HidrawTransport()
