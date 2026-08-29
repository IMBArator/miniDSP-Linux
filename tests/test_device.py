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

import pytest

from minidsp import protocol, transport
from minidsp.device import DeviceClosedError, DSPmini, DeviceLockedError
from minidsp.protocol import REPORT_SIZE
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
