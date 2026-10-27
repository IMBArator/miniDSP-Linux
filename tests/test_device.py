"""Tests for :mod:`minidsp.device` and :mod:`minidsp.transport`.

The device layer is exercised through a :class:`FakeTransport` — the transport
split (``minidsp/transport.py``) exists precisely so the request/response logic
can be driven without hardware. Two modes are available:

* **scripted**: a queue of reports handed out in order, ``None`` meaning
  "read timed out";
* **responder**: a callback that receives every report the device layer sends
  and returns the reply, which is what multi-exchange flows such as
  ``read_config`` need.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from minidsp import device as device_module
from minidsp import protocol, transport
from minidsp.device import (
    DeviceBusyError,
    DeviceClosedError,
    DSPmini,
    DeviceLockedError,
)
from minidsp.protocol import REPORT_SIZE
from minidsp.unt import UntFile
from minidsp.transport import (
    HidapiTransport,
    HidrawTransport,
    Transport,
    default_transport,
)


# --- Helpers ---------------------------------------------------------------

def device_frame(payload: bytes) -> bytes:
    """Build a device→host report carrying ``payload``.

    Reuses :func:`~minidsp.protocol.build_frame` (identical framing and
    checksum) and swaps the SRC/DST bytes so the frame reads as coming from
    the device, the way a real reply does.

    Args:
        payload: Response payload, starting with the opcode byte.

    Returns:
        A zero-padded report of :data:`~minidsp.protocol.REPORT_SIZE` bytes.
    """
    frame = bytearray(protocol.build_frame(payload))
    frame[2], frame[3] = frame[3], frame[2]
    return bytes(frame)


ACK = device_frame(b"\x01")
NACK = device_frame(b"\x00")


def request_opcode(report: bytes) -> int:
    """Return the opcode of a host→device report."""
    return report[5]


class FakeTransport(Transport):
    """In-memory transport that records writes and replays scripted replies.

    Args:
        reads: Reply reports handed to successive :meth:`read` calls.
            A ``None`` entry simulates a read timeout. Exhausting the list
            also yields ``None``.
        responder: Callback invoked with each sent report, returning the
            reply report (or ``None`` for a timeout). Takes precedence over
            ``reads``; use it for flows with many exchanges.

    Attributes:
        sent: Every report passed to :meth:`write`, in order.
        timeouts: Every ``timeout_ms`` value passed to :meth:`read`.
        open_calls: Device paths passed to :meth:`open`.
        close_calls: Number of :meth:`close` calls.
    """

    def __init__(self, reads=None, responder=None) -> None:
        self.reads: list[bytes | None] = list(reads or [])
        self.responder = responder
        self.sent: list[bytes] = []
        self.timeouts: list[int] = []
        self.open_calls: list[str | None] = []
        self.close_calls = 0
        self._open = False
        self._pending: list[bytes | None] = []

    @staticmethod
    def find_device() -> str | None:
        return "fake"

    def open(self, device_path: str | None = None) -> None:
        self.open_calls.append(device_path)
        self._open = True

    def close(self) -> None:
        self.close_calls += 1
        self._open = False

    def write(self, report: bytes) -> None:
        if not self._open:
            raise DeviceClosedError("Device not open")
        self.sent.append(report)
        if self.responder is not None:
            reply = self.responder(report)
            if isinstance(reply, list):
                self._pending.extend(reply)
            else:
                self._pending.append(reply)

    def read(self, timeout_ms: int = 500) -> bytes | None:
        if not self._open:
            raise DeviceClosedError("Device not open")
        self.timeouts.append(timeout_ms)
        if self.responder is not None:
            return self._pending.pop(0) if self._pending else None
        return self.reads.pop(0) if self.reads else None

    @property
    def is_open(self) -> bool:
        return self._open


def opened_device(**kwargs) -> tuple[DSPmini, FakeTransport]:
    """Return a :class:`DSPmini` with an already-open :class:`FakeTransport`.

    Bypasses :meth:`DSPmini.open` (and its init handshake) so command tests
    do not have to script the handshake exchange.
    """
    fake = FakeTransport(**kwargs)
    dsp = DSPmini(transport=fake)
    fake.open()
    return dsp, fake


# --- open() / init handshake (ADR-0013) ------------------------------------

def test_open_succeeds_on_last_init_attempt(monkeypatch):
    monkeypatch.setattr("minidsp.device.time.sleep", lambda _s: None)
    fake = FakeTransport(reads=[None, None, None, None, ACK])
    dsp = DSPmini(transport=fake)

    dsp.open()

    assert fake.open_calls == [None]
    assert len(fake.sent) == 5
    assert all(request_opcode(r) == protocol.OP_INIT for r in fake.sent)
    assert fake.close_calls == 0


def test_open_raises_and_closes_after_five_failed_init_attempts(monkeypatch):
    monkeypatch.setattr("minidsp.device.time.sleep", lambda _s: None)
    fake = FakeTransport(reads=[None] * 5)
    dsp = DSPmini(transport=fake)

    with pytest.raises(OSError, match="not responding to init handshake"):
        dsp.open()

    assert len(fake.sent) == 5
    assert fake.close_calls == 1
    assert not fake.is_open


def test_open_passes_explicit_device_path_to_transport(monkeypatch):
    monkeypatch.setattr("minidsp.device.time.sleep", lambda _s: None)
    fake = FakeTransport(reads=[ACK])
    DSPmini(transport=fake).open("/dev/hidraw9")

    assert fake.open_calls == ["/dev/hidraw9"]


def test_context_manager_closes_transport(monkeypatch):
    monkeypatch.setattr("minidsp.device.time.sleep", lambda _s: None)
    fake = FakeTransport(reads=[ACK])

    with DSPmini(transport=fake) as dsp:
        assert isinstance(dsp, DSPmini)
        assert fake.is_open

    assert fake.close_calls == 1


def test_default_transport_is_used_when_none_given(monkeypatch):
    made: list[Transport] = []

    def fake_default():
        t = FakeTransport()
        made.append(t)
        return t

    monkeypatch.setattr("minidsp.device.default_transport", fake_default)
    dsp = DSPmini()

    assert dsp._transport is made[0]


# --- Closed-handle errors (ADR-0014) ---------------------------------------

def test_send_after_close_raises_device_closed_error():
    dsp, _fake = opened_device()
    dsp.close()

    with pytest.raises(DeviceClosedError):
        dsp._send(protocol.cmd_init())


def test_recv_after_close_raises_device_closed_error():
    dsp, _fake = opened_device()
    dsp.close()

    with pytest.raises(DeviceClosedError):
        dsp._recv()


def test_device_closed_error_is_catchable_as_oserror():
    dsp, _fake = opened_device()
    dsp.close()

    with pytest.raises(OSError):
        dsp.poll_levels()


# --- Device-busy errors (ADR-0012 / ADR-0024) ------------------------------

class BusyTransport(FakeTransport):
    """A :class:`FakeTransport` whose :meth:`open` reports a lock conflict."""

    def open(self, device_path: str | None = None) -> None:
        self.open_calls.append(device_path)
        raise DeviceBusyError(f"{device_path} is already in use by another process")


def test_device_busy_error_is_an_oserror_and_reexported():
    # OSError subclassing keeps every existing ``except OSError`` caller
    # working, and device.py must re-export the same object, not a copy.
    assert issubclass(DeviceBusyError, OSError)
    assert device_module.DeviceBusyError is transport.DeviceBusyError


def test_dspmini_open_propagates_device_busy(monkeypatch):
    monkeypatch.setattr("minidsp.device.time.sleep", lambda _s: None)
    busy = BusyTransport()
    dsp = DSPmini(transport=busy)

    # The init-handshake retry loop must not swallow or retype this.
    with pytest.raises(DeviceBusyError, match="already in use"):
        dsp.open()

    assert busy.sent == []
    assert busy.close_calls == 0


@pytest.mark.skipif(sys.platform == "win32", reason="flock is POSIX-only")
def test_hidraw_open_raises_device_busy_when_flock_is_held(monkeypatch):
    closed: list[int] = []

    def refuse_lock(_fd, _operation):
        raise BlockingIOError("Resource temporarily unavailable")

    monkeypatch.setattr(transport.os, "open", lambda _path, _flags: 42)
    monkeypatch.setattr(transport.os, "close", closed.append)
    monkeypatch.setattr(transport.fcntl, "flock", refuse_lock)
    t = HidrawTransport()

    with pytest.raises(DeviceBusyError, match="already in use"):
        t.open("/dev/hidraw0")

    # The fd is handed back before raising, so the caller need not close().
    assert closed == [42]
    assert t._fd is None
    assert t.is_open is False


@pytest.mark.skipif(sys.platform != "win32",
                    reason="ctypes.WinDLL/get_last_error are Windows-only")
def test_hidapi_acquire_mutex_raises_device_busy_when_mutex_exists(monkeypatch):
    import ctypes

    class FakeWin32Func:
        """Callable stand-in for a kernel32 export, recording its calls."""

        def __init__(self, result: int) -> None:
            self.result = result
            self.restype = None
            self.calls: list[tuple] = []

        def __call__(self, *args):
            self.calls.append(args)
            return self.result

    class FakeKernel32:
        """The two kernel32 entry points ``_acquire_mutex`` touches."""

        def __init__(self) -> None:
            self.CreateMutexW = FakeWin32Func(1)   # a non-NULL handle
            self.CloseHandle = FakeWin32Func(1)

    kernel32 = FakeKernel32()
    monkeypatch.setattr(ctypes, "WinDLL",
                        lambda _name, use_last_error=False: kernel32)
    monkeypatch.setattr(ctypes, "get_last_error",
                        lambda: HidapiTransport._ERROR_ALREADY_EXISTS)
    t = HidapiTransport()

    with pytest.raises(DeviceBusyError, match="already in use"):
        t._acquire_mutex("\\\\?\\hid#vid_0168&pid_0821")

    # The handle CreateMutexW still returned must not leak.
    assert len(kernel32.CloseHandle.calls) == 1
    assert t._mutex is None


# --- Response validation (ADR-0015) ----------------------------------------

def test_set_gain_true_on_ack():
    dsp, fake = opened_device(reads=[ACK])

    assert dsp.set_gain(0, 320) is True
    assert request_opcode(fake.sent[0]) == protocol.OP_GAIN


def test_set_gain_false_on_timeout():
    dsp, _fake = opened_device(reads=[None])

    assert dsp.set_gain(0, 320) is False


def test_mute_false_on_nack():
    dsp, _fake = opened_device(reads=[NACK])

    assert dsp.mute(0, True) is False


def test_send_recv_returns_none_on_unparseable_frame():
    dsp, _fake = opened_device(reads=[b"\xff" * REPORT_SIZE])

    assert dsp.poll_levels() is None


def test_skip_polls_discards_interleaved_level_response():
    poll_frame = device_frame(bytes([protocol.OP_POLL]) + bytes(27))
    dsp, _fake = opened_device(reads=[poll_frame, ACK])

    payload = dsp._send_recv(protocol.cmd_activate(), skip_polls=True)

    assert payload == b"\x01"


def test_poll_response_is_kept_when_skip_polls_is_off():
    poll_frame = device_frame(bytes([protocol.OP_POLL]) + bytes(27))
    dsp, _fake = opened_device(reads=[poll_frame])

    levels = dsp.poll_levels()

    assert levels is not None
    assert len(levels["inputs"]) == 4


# --- read_config -----------------------------------------------------------

FIRMWARE_PAYLOAD = b"\x134x4MINI V010"


def make_config_blob() -> bytes:
    """Build a 450-byte config blob with a few recognisable values."""
    blob = bytearray(protocol.CONFIG_PAGES * protocol.CONFIG_PAGE_SIZE)
    blob[16:19] = b"IN1"                       # input 1 channel name
    blob[16 + 18] = 320 % 256                  # input 1 gain (uint16 LE)
    blob[16 + 19] = 320 // 256
    blob[408] = 0x01                           # input mute bitmask: In1 muted
    return bytes(blob)


def config_responder(config_blob: bytes, locked: bool = False,
                     fail_opcode: int | None = None):
    """Return a responder emulating the 8-step ``read_config`` sequence.

    Args:
        config_blob: 450-byte config the device should hand back, split into
            ``0x24`` page responses.
        locked: When ``True``, the ``0x2C`` reply carries the lock byte.
        fail_opcode: Opcode to answer with a timeout (``None`` reply).
    """
    def respond(report: bytes) -> bytes | None:
        op = request_opcode(report)
        if op == fail_opcode:
            return None
        if op == protocol.OP_FIRMWARE:
            return device_frame(FIRMWARE_PAYLOAD)
        if op == protocol.OP_DEVICE_INFO:
            return device_frame(bytes([protocol.OP_DEVICE_INFO, 0, 0, 0, 0, 0,
                                       0x01 if locked else 0x00]))
        if op == protocol.OP_PRESET_INDEX:
            return device_frame(bytes([protocol.OP_PRESET_INDEX, 3]))
        if op == protocol.OP_READ_NAME:
            index = report[6]
            name = f"PRESET{index:02d}".ljust(14).encode("ascii")
            return device_frame(bytes([protocol.OP_READ_NAME, index]) + name)
        if op == protocol.OP_READ_CONFIG:
            page = report[6]
            start = page * protocol.CONFIG_PAGE_SIZE
            data = config_blob[start:start + protocol.CONFIG_PAGE_SIZE]
            return device_frame(bytes([protocol.OP_CONFIG_RESP, page]) + data)
        return ACK  # preset header, activate, …
    return respond


def test_read_config_happy_path():
    blob = make_config_blob()
    dsp, fake = opened_device(responder=config_responder(blob))

    cfg = dsp.read_config()

    assert cfg is not None
    assert cfg["names"][0] == "IN1"
    assert cfg["gains"][0] == 320
    assert cfg["mutes"][0] is True
    assert cfg["active_slot"] == 3
    assert cfg["preset_names"][0] == "PRESET00"
    assert len(cfg["preset_names"]) == 30
    assert cfg["firmware"]["model"] == "4x4MINI"
    assert cfg["firmware"]["version"] == "V010"
    # All 9 config pages were requested, in order.
    pages = [r[6] for r in fake.sent if request_opcode(r) == protocol.OP_READ_CONFIG]
    assert pages == list(range(protocol.CONFIG_PAGES))


def test_read_config_returns_none_when_firmware_query_times_out():
    dsp, fake = opened_device(
        responder=config_responder(make_config_blob(),
                                   fail_opcode=protocol.OP_FIRMWARE))

    assert dsp.read_config() is None
    # Early exit: nothing beyond the firmware query was attempted.
    assert [request_opcode(r) for r in fake.sent] == [protocol.OP_FIRMWARE]


def test_read_config_returns_none_when_a_config_page_times_out():
    dsp, _fake = opened_device(
        responder=config_responder(make_config_blob(),
                                   fail_opcode=protocol.OP_READ_CONFIG))

    assert dsp.read_config() is None


def test_read_config_raises_device_locked_error_on_lock_byte():
    dsp, _fake = opened_device(
        responder=config_responder(make_config_blob(), locked=True))

    with pytest.raises(DeviceLockedError, match="submit_pin"):
        dsp.read_config()


def test_is_locked_reads_the_lock_byte():
    info = bytes([protocol.OP_DEVICE_INFO, 0, 0, 0, 0, 0, 0x01])
    dsp, _fake = opened_device(reads=[device_frame(info)])

    assert dsp.is_locked() is True


# --- store_preset (ADR-0015) -----------------------------------------------

def name_echo(name: str) -> bytes:
    """Build the 16-byte 0x26 name echo the device answers with."""
    return device_frame(b"\x01\x02" + name.ljust(14).encode("ascii"))


def test_store_preset_happy_path_uses_three_second_store_timeout():
    dsp, fake = opened_device(reads=[name_echo("MY PRESET"), ACK, ACK])

    assert dsp.store_preset(5, "MY PRESET") is True
    assert 3000 in fake.timeouts
    assert [request_opcode(r) for r in fake.sent] == [
        protocol.OP_STORE_NAME, protocol.OP_STORE_PRESET, protocol.OP_ACTIVATE]


def test_store_preset_false_when_name_command_is_not_echoed():
    dsp, fake = opened_device(reads=[NACK])

    assert dsp.store_preset(5, "MY PRESET") is False
    # Aborts before sending the store command.
    assert [request_opcode(r) for r in fake.sent] == [protocol.OP_STORE_NAME]


def test_store_preset_continues_but_warns_on_name_echo_mismatch(caplog):
    dsp, _fake = opened_device(reads=[name_echo("OTHER"), ACK, ACK])

    with caplog.at_level(logging.WARNING, logger="minidsp.device"):
        assert dsp.store_preset(5, "MY PRESET") is True

    assert "echo mismatch" in caplog.text


def test_store_preset_false_when_store_command_is_not_acked():
    dsp, _fake = opened_device(reads=[name_echo("MY PRESET"), NACK])

    assert dsp.store_preset(5, "MY PRESET") is False


def test_store_preset_false_when_activate_is_not_acked():
    dsp, _fake = opened_device(reads=[name_echo("MY PRESET"), ACK, None])

    assert dsp.store_preset(5, "MY PRESET") is False


# --- Transport selection ---------------------------------------------------

def test_default_transport_on_linux_is_hidraw(monkeypatch):
    monkeypatch.setattr(transport.sys, "platform", "linux")

    assert isinstance(default_transport(), HidrawTransport)


def test_hidraw_transport_reports_closed_state():
    t = HidrawTransport()

    assert t.is_open is False
    with pytest.raises(DeviceClosedError):
        t.write(b"\x00" * REPORT_SIZE)
    with pytest.raises(DeviceClosedError):
        t.read()
    t.close()  # closing an unopened transport is a no-op


def test_hidraw_find_device_returns_none_without_matching_sysfs_entry(monkeypatch):
    monkeypatch.setattr(transport.glob, "glob", lambda _pattern: [])

    assert HidrawTransport.find_device() is None


def test_default_transport_on_windows_is_hidapi(monkeypatch):
    monkeypatch.setattr(transport.sys, "platform", "win32")

    assert isinstance(default_transport(), HidapiTransport)


# --- HidapiTransport (Windows), exercised off-Windows via a hid stub -------

class StubHidDevice:
    """Stand-in for ``hid.device()`` recording writes and replaying reads."""

    def __init__(self, reads=None) -> None:
        self.reads = list(reads or [])
        self.written: list[bytes] = []
        self.read_args: list[tuple[int, int]] = []
        self.opened_path: bytes | None = None
        self.closed = False

    def open_path(self, path: bytes) -> None:
        self.opened_path = path

    def write(self, data: bytes) -> int:
        self.written.append(bytes(data))
        return len(data)

    def read(self, size: int, timeout_ms: int = 0):
        self.read_args.append((size, timeout_ms))
        return self.reads.pop(0) if self.reads else []

    def close(self) -> None:
        self.closed = True


class StubHidModule:
    """Minimal stand-in for the ``hid`` module injected via ``sys.modules``."""

    def __init__(self, device: StubHidDevice, entries=None) -> None:
        self._device = device
        self._entries = entries or []

    def device(self) -> StubHidDevice:
        return self._device

    def enumerate(self, vendor_id: int = 0, product_id: int = 0):
        return self._entries


@pytest.fixture
def hid_stub(monkeypatch):
    """Install a stub ``hid`` module and return its device stub."""
    device = StubHidDevice()
    monkeypatch.setitem(sys.modules, "hid", StubHidModule(device))
    return device


def test_hidapi_write_prepends_report_number(hid_stub):
    t = HidapiTransport()
    t._dev = hid_stub
    report = protocol.cmd_init()

    t.write(report)

    assert len(hid_stub.written[0]) == REPORT_SIZE + 1
    assert hid_stub.written[0][0] == 0x00
    assert hid_stub.written[0][1:] == report


def test_hidapi_read_returns_bare_data_bytes(hid_stub):
    hid_stub.reads.append(list(ACK))
    t = HidapiTransport()
    t._dev = hid_stub

    data = t.read(timeout_ms=2000)

    assert data == ACK
    assert hid_stub.read_args == [(REPORT_SIZE, 2000)]


def test_hidapi_read_maps_empty_list_to_none(hid_stub):
    t = HidapiTransport()
    t._dev = hid_stub

    assert t.read(timeout_ms=500) is None


def test_hidapi_reports_closed_state(hid_stub):
    t = HidapiTransport()

    assert t.is_open is False
    with pytest.raises(DeviceClosedError):
        t.write(b"\x00" * REPORT_SIZE)
    with pytest.raises(DeviceClosedError):
        t.read()
    t.close()  # closing an unopened transport is a no-op


def test_hidapi_close_closes_the_hid_device(hid_stub):
    t = HidapiTransport()
    t._dev = hid_stub

    t.close()

    assert hid_stub.closed is True
    assert t.is_open is False


def test_hidapi_find_device_returns_first_enumerated_path(monkeypatch):
    entries = [
        {"path": b"\\\\?\\hid#vid_0168&pid_0821#1", "interface_number": 0,
         "usage_page": 0xFF00, "usage": 0x01},
        {"path": b"\\\\?\\hid#vid_0168&pid_0821#2", "interface_number": 1,
         "usage_page": 0x000C, "usage": 0x01},
    ]
    monkeypatch.setitem(sys.modules, "hid",
                        StubHidModule(StubHidDevice(), entries=entries))

    assert HidapiTransport.find_device() == "\\\\?\\hid#vid_0168&pid_0821#1"


def test_hidapi_find_device_returns_none_when_not_connected(hid_stub):
    assert HidapiTransport.find_device() is None


# --- .unt save / restore (ADR-0026) ----------------------------------------
# The fake device serves names, the 0x19 header block and stored pages from
# the file the editor wrote during capture_20261026_221454.

UNT_261026 = (Path(__file__).resolve().parent.parent / "analysis"
              / "miniDSP current settings 261026.unt")
# 0x1a frame the editor sent in capture_20261026_222715 (restoring that file)
CAPTURED_HEADER_WRITE = bytes.fromhex(
    "10020001251a010021031e303030300000270f000041534446000a00"
    "3478344420416d706c696669657210036d")
# First 0x25 write of that capture: page 0 of U01
CAPTURED_FIRST_PAGE_WRITE = bytes.fromhex(
    "250000ffff444959204d6f6e20202020202020496e41000000000000003100f301630000"
    "00180100000300496e4200000000000000")


def unt_fixture() -> UntFile:
    if not UNT_261026.exists():
        pytest.skip("miniDSP current settings 261026.unt not present")
    return UntFile.read(UNT_261026)


def unt_device_responder(unt: UntFile, device_pin: bytes = b"ASDF",
                         fail_opcode: int | None = None):
    """Return a responder emulating a device that holds ``unt``'s presets."""
    header = protocol.device_header_with_pin(unt.header_block, device_pin)
    selected = {"slot": None}

    def respond(report: bytes) -> bytes | None:
        op = request_opcode(report)
        if op == fail_opcode:
            return None
        if op == protocol.OP_READ_NAME:
            index = report[6]
            name = unt.slot_name(index + 1) or "Default Preset"
            return device_frame(bytes([op, index]) + name.ljust(14).encode("ascii"))
        if op == protocol.OP_DEVICE_HEADER:
            return device_frame(bytes([op]) + header)
        if op == protocol.OP_SELECT_STORED:
            selected["slot"] = report[6]
            return ACK
        if op == protocol.OP_READ_STORED_PAGE:
            page = report[6]
            raw = unt.slot_blob(selected["slot"]) + bytes(21)   # 450-byte device form
            return device_frame(bytes([op, page]) + raw[page * 50:(page + 1) * 50])
        if op == protocol.OP_WRITE_STORED_PAGE:
            return device_frame(bytes([op, report[6]]))
        if op == protocol.OP_REBOOT:
            return None
        return ACK   # activate, begin restore, header write
    return respond


def frame(report: bytes) -> bytes:
    return report[:5 + report[4] + 3]


def test_export_unt_matches_the_editor_file():
    unt = unt_fixture()
    dsp, fake = opened_device(responder=unt_device_responder(unt))

    exported = dsp.export_unt()

    assert exported is not None
    assert exported.to_bytes() == unt.to_bytes()
    ops = [request_opcode(r) for r in fake.sent]
    assert ops[:30] == [protocol.OP_READ_NAME] * 30
    per_slot = [protocol.OP_SELECT_STORED] + [protocol.OP_READ_STORED_PAGE] * 9
    assert ops[30:] == [protocol.OP_DEVICE_HEADER] + per_slot * 4 + [protocol.OP_ACTIVATE]
    selects = [r[6] for r in fake.sent if request_opcode(r) == protocol.OP_SELECT_STORED]
    assert selects == [1, 2, 3, 30]
    # never a recall
    assert protocol.OP_LOAD_PRESET not in ops


def test_read_stored_preset_returns_raw_blob_and_params():
    unt = unt_fixture()
    dsp, _fake = opened_device(responder=unt_device_responder(unt))

    preset = dsp.read_stored_preset(2)

    assert preset["name"] == "DIY Mon offset"
    assert len(preset["raw"]) == 450
    assert preset["unt_blob"] == unt.slot_blob(2)
    assert preset["params"] == unt.slot_params(2)


def test_read_stored_presets_validates_slots_before_any_io():
    dsp, fake = opened_device(responder=lambda report: ACK)
    with pytest.raises(ValueError):
        dsp.read_stored_presets([1, 0])
    assert fake.sent == []


def test_read_stored_presets_failure_still_sends_activate():
    unt = unt_fixture()
    dsp, fake = opened_device(responder=unt_device_responder(
        unt, fail_opcode=protocol.OP_READ_STORED_PAGE))

    assert dsp.read_stored_presets([1]) is None
    assert request_opcode(fake.sent[-1]) == protocol.OP_ACTIVATE


def test_restore_unt_requires_confirm():
    unt = unt_fixture()
    dsp, fake = opened_device(responder=unt_device_responder(unt))
    with pytest.raises(ValueError, match="confirm"):
        dsp.restore_unt(unt)
    assert fake.sent == []


def test_restore_unt_refuses_a_file_without_presets():
    dsp, fake = opened_device(responder=lambda report: ACK)
    with pytest.raises(ValueError, match="no presets"):
        dsp.restore_unt(UntFile.blank(), confirm=True)
    assert fake.sent == []


def test_restore_unt_sends_the_editor_sequence_and_closes():
    unt = unt_fixture()
    dsp, fake = opened_device(responder=unt_device_responder(unt))

    assert dsp.restore_unt(unt, confirm=True) is True

    ops = [request_opcode(r) for r in fake.sent]
    assert ops == ([protocol.OP_DEVICE_HEADER, protocol.OP_RESTORE_BEGIN,
                    protocol.OP_WRITE_DEVICE_HEADER]
                   + [protocol.OP_WRITE_STORED_PAGE] * 36 + [protocol.OP_REBOOT])
    # device PIN == file PIN here, so the header write equals the captured frame
    assert frame(fake.sent[2]) == CAPTURED_HEADER_WRITE
    writes = [frame(r) for r in fake.sent if request_opcode(r) == protocol.OP_WRITE_STORED_PAGE]
    assert writes[0][5:-3] == CAPTURED_FIRST_PAGE_WRITE
    assert [(w[6], w[7]) for w in writes[::9]] == [(0, 0), (0, 1), (0, 2), (0, 29)]
    assert {len(w) for w in writes[8::9]} == {5 + 22 + 3}     # page 8: 19 data bytes
    assert 3000 in fake.timeouts                               # 0x23 waits ~1.6 s
    assert not fake.is_open


def test_restore_unt_keeps_the_device_pin_by_default():
    unt = unt_fixture()                                        # file PIN "ASDF"
    dsp, fake = opened_device(responder=unt_device_responder(unt, device_pin=b"1234"))

    assert dsp.restore_unt(unt, confirm=True) is True
    header_write = fake.sent[2]
    assert header_write[5 + 16:5 + 20] == b"1234"              # .unt 0x1D–0x20


def test_restore_unt_can_write_the_file_pin():
    unt = unt_fixture()
    dsp, fake = opened_device(responder=unt_device_responder(unt, device_pin=b"1234"))

    assert dsp.restore_unt(unt, confirm=True, keep_device_pin=False) is True
    assert request_opcode(fake.sent[0]) == protocol.OP_RESTORE_BEGIN   # no 0x19 read
    assert frame(fake.sent[1]) == CAPTURED_HEADER_WRITE


def test_restore_unt_of_an_f00_active_file_matches_the_capture():
    # capture_20261027_103133: the editor restores a file saved with F00
    # active; its 0x1a header write carries active slot 0 and is ACKed.
    path = UNT_261026.with_name("miniDSP current settings 261027 - F00 active.unt")
    if not path.exists():
        pytest.skip(f"{path.name} not present")
    unt = UntFile.read(path)
    dsp, fake = opened_device(responder=unt_device_responder(unt))

    assert dsp.restore_unt(unt, confirm=True) is True
    assert frame(fake.sent[2]) == bytes.fromhex(
        "10020001251a010021001e303030300000270f000041534446000a00"
        "3478344420416d706c696669657210036e")


def test_restore_unt_stops_on_a_missing_page_echo():
    unt = unt_fixture()
    dsp, fake = opened_device(responder=unt_device_responder(
        unt, fail_opcode=protocol.OP_WRITE_STORED_PAGE))

    assert dsp.restore_unt(unt, confirm=True) is False
    assert protocol.OP_REBOOT not in [request_opcode(r) for r in fake.sent]
    assert fake.is_open
