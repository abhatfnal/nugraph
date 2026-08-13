"""Unit tests for pywcml.eventgraph_ipc wire-format encode/decode.

Tests use a socketpair (AF_UNIX, SOCK_STREAM) to push bytes from an
in-process encoder (simulating C++ TensorSetLabeler) to the Python
decoder, verifying round-trip fidelity without running lar.

Run with:
    pytest pywcml/tests/test_eventgraph_ipc.py -v
"""

from __future__ import annotations

import socket
import struct
import threading
from dataclasses import dataclass, field
from typing import Final

import numpy as np
import pytest

from pywcml.eventgraph_ipc import (
    ACK,
    DTYPE_FLOAT32_LE,
    DTYPE_INT64_LE,
    END_OF_STREAM,
    ERROR,
    EVENT_GRAPH,
    EVENT_GRAPH_SCHEMA_VERSION,
    MAGIC,
    PROTOCOL_VERSION,
    EventGraphIPCError,
    EventGraphIdentity,
    ReceivedEventGraph,
    _ENV,
    _U8,
    _U16,
    _U32,
    _U64,
    create_server_socket,
    receive_event_graph,
    send_ack,
    send_error,
    serve_one_connection,
)


# ---- minimal C++-side encoder (pure Python) --------------------------------

def _le32(v: int) -> bytes:
    return struct.pack("<I", v)

def _le64(v: int) -> bytes:
    return struct.pack("<Q", v)

def _le16(v: int) -> bytes:
    return struct.pack("<H", v)

def _u8(v: int) -> bytes:
    return struct.pack("<B", v)

def _str_field(s: str) -> bytes:
    b = s.encode("ascii")
    return _le32(len(b)) + b

def _encode_member(name: str, arr: np.ndarray) -> bytes:
    """Encode one H5Member into wire bytes."""
    if arr.dtype == np.dtype("<f4") or arr.dtype == np.float32:
        arr = arr.astype("<f4")
        dtype_code = DTYPE_FLOAT32_LE
    elif arr.dtype == np.dtype("<i8") or arr.dtype == np.int64:
        arr = arr.astype("<i8")
        dtype_code = DTYPE_INT64_LE
    else:
        raise ValueError(f"unsupported test dtype {arr.dtype}")

    raw = arr.tobytes()
    rank = arr.ndim
    dims = arr.shape if rank > 0 else ()

    out = _str_field(name)
    out += _u8(dtype_code)
    out += _u8(rank)
    out += _le16(0)  # reserved
    for d in dims:
        out += _le64(d)
    out += _le64(len(raw))
    out += raw
    return out


def _encode_event_graph(
    sample_name: str,
    run: int, sub: int, evt: int,
    has_truth: bool,
    members: list[tuple[str, np.ndarray]],
) -> bytes:
    """Encode a complete EVENT_GRAPH wire message."""
    payload = b""
    payload += _le32(EVENT_GRAPH_SCHEMA_VERSION)
    payload += _le32(1 if has_truth else 0)
    payload += _str_field(sample_name)
    payload += _le32(len(members))
    for name, arr in members:
        payload += _encode_member(name, arr)

    env = _ENV.pack(MAGIC, PROTOCOL_VERSION, EVENT_GRAPH, len(payload),
                    run, sub, evt)
    return env + payload


def _encode_eos(run: int, sub: int, evt: int) -> bytes:
    return _ENV.pack(MAGIC, PROTOCOL_VERSION, END_OF_STREAM, 0, run, sub, evt)


def _send_and_receive(members: list[tuple[str, np.ndarray]],
                      sample_name: str = "1_2728_1__rec-lab-apa0-1",
                      run: int = 1, sub: int = 2728, evt: int = 1,
                      has_truth: bool = True) -> ReceivedEventGraph:
    """Send one EVENT_GRAPH through a socketpair and decode it."""
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    msg = _encode_event_graph(sample_name, run, sub, evt, has_truth, members)
    try:
        a.sendall(msg)
        result = receive_event_graph(b)
        return result
    finally:
        a.close()
        b.close()


# ---- tests: happy path -----------------------------------------------------

class TestBasicDecode:
    def test_float32_1d(self):
        arr = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        r = _send_and_receive([("sp/features", arr)])
        assert "sp/features" in r.arrays
        result = r.arrays["sp/features"]
        assert result.dtype == np.dtype("<f4")
        np.testing.assert_array_equal(result, arr)

    def test_int64_1d(self):
        arr = np.array([0, 1, 2, 100], dtype=np.int64)
        r = _send_and_receive([("metadata/run", arr)])
        result = r.arrays["metadata/run"]
        assert result.dtype == np.dtype("<i8")
        np.testing.assert_array_equal(result, arr)

    def test_float32_2d(self):
        arr = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], dtype=np.float32)
        r = _send_and_receive([("sp/pos", arr)])
        result = r.arrays["sp/pos"]
        assert result.shape == (2, 3)
        np.testing.assert_array_equal(result, arr)

    def test_int64_2d(self):
        arr = np.arange(12, dtype=np.int64).reshape(2, 6)
        r = _send_and_receive([("sp_nexus_sp/edge_index", arr)])
        result = r.arrays["sp_nexus_sp/edge_index"]
        assert result.shape == (2, 6)
        np.testing.assert_array_equal(result, arr)

    def test_scalar_float32(self):
        # rank=0: scalar stored as 1-element array, reshaped to ()
        arr = np.array([3.14], dtype=np.float32)
        r = _send_and_receive([("scalar_f", arr.reshape(()))])
        result = r.arrays["scalar_f"]
        assert result.shape == ()
        np.testing.assert_almost_equal(float(result), 3.14, decimal=5)

    def test_scalar_int64(self):
        arr = np.array([42], dtype=np.int64).reshape(())
        r = _send_and_receive([("metadata/run", arr)])
        result = r.arrays["metadata/run"]
        assert result.shape == ()
        assert int(result) == 42

    def test_multiple_members(self):
        members = [
            ("sp/pos", np.zeros((10, 3), dtype=np.float32)),
            ("sp/features", np.ones((10, 6), dtype=np.float32)),
            ("sp/truth", np.arange(10, dtype=np.int64)),
        ]
        r = _send_and_receive(members)
        assert set(r.arrays.keys()) == {"sp/pos", "sp/features", "sp/truth"}
        assert r.arrays["sp/pos"].shape == (10, 3)

    def test_identity_fields(self):
        r = _send_and_receive([], run=7, sub=99, evt=3, has_truth=False)
        assert r.identity.run    == 7
        assert r.identity.subrun == 99
        assert r.identity.event  == 3
        assert r.has_truth is False

    def test_sample_name(self):
        r = _send_and_receive([], sample_name="7_99_3__rec-lab-apa0-1")
        assert r.sample_name == "7_99_3__rec-lab-apa0-1"

    def test_zero_length_1d(self):
        # Empty 1D array: shape (0,) — e.g., no supervision edges
        arr = np.zeros((0,), dtype=np.int64)
        r = _send_and_receive([("empty/edges", arr)])
        result = r.arrays["empty/edges"]
        assert result.shape == (0,)

    def test_zero_length_2d(self):
        arr = np.zeros((2, 0), dtype=np.int64)
        r = _send_and_receive([("edge_index", arr)])
        result = r.arrays["edge_index"]
        assert result.shape == (2, 0)

    def test_float32_exact_bytes(self):
        # Verify no float32 -> float64 widening on decode
        import struct as st
        raw_float = st.pack("<f", 1.0 / 3.0)
        arr = np.frombuffer(raw_float, dtype="<f4")
        r = _send_and_receive([("frac", arr)])
        result_bytes = r.arrays["frac"].tobytes()
        assert result_bytes == raw_float

    def test_int64_extreme_values(self):
        arr = np.array([-2**63, 2**63 - 1, 0, -1], dtype=np.int64)
        r = _send_and_receive([("extreme", arr)])
        np.testing.assert_array_equal(r.arrays["extreme"], arr)


# ---- tests: ACK / ERROR / END_OF_STREAM -----------------------------------

class TestAckAndError:
    def test_send_ack(self):
        a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            identity = EventGraphIdentity(1, 2728, 1)
            send_ack(a, identity)
            raw = b.recv(32)
            assert len(raw) == 32
            magic, ver, kind, plen, run, sub, evt = _ENV.unpack(raw)
            assert magic == MAGIC
            assert ver   == PROTOCOL_VERSION
            assert kind  == ACK
            assert plen  == 0
            assert run   == 1
            assert sub   == 2728
            assert evt   == 1
        finally:
            a.close(); b.close()

    def test_send_error(self):
        a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            identity = EventGraphIdentity(1, 2728, 1)
            send_error(a, identity, "test error")
            raw = b.recv(4096)
            magic, ver, kind, plen, run, sub, evt = _ENV.unpack(raw[:32])
            assert kind == ERROR
            msg_len = _U32.unpack(raw[32:36])[0]
            msg = raw[36:36 + msg_len].decode("utf-8")
            assert msg == "test error"
        finally:
            a.close(); b.close()


# ---- tests: protocol violation detection ----------------------------------

class TestProtocolViolations:
    def _tamper_and_decode(self, msg: bytes, offset: int, value: bytes) -> None:
        """Replace bytes at offset with value, then decode — expect error."""
        tampered = bytearray(msg)
        tampered[offset:offset + len(value)] = value
        a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            a.sendall(bytes(tampered))
            with pytest.raises(EventGraphIPCError):
                receive_event_graph(b)
        finally:
            a.close(); b.close()

    def test_bad_magic(self):
        msg = _encode_event_graph("s", 1, 1, 1, True, [])
        # Corrupt first byte of magic
        self._tamper_and_decode(msg, 0, b"X")

    def test_wrong_version(self):
        msg = _encode_event_graph("s", 1, 1, 1, True, [])
        # version is at offset 8 (uint16 LE)
        self._tamper_and_decode(msg, 8, struct.pack("<H", 99))

    def test_wrong_msg_type(self):
        msg = _encode_event_graph("s", 1, 1, 1, True, [])
        # msg_type is at offset 10 (uint16 LE); set to ACK(5)
        self._tamper_and_decode(msg, 10, struct.pack("<H", ACK))

    def test_schema_version_mismatch(self):
        msg = _encode_event_graph("s", 1, 1, 1, True, [])
        # schema_version is at envelope(32) + 0; set to 99
        self._tamper_and_decode(msg, 32, struct.pack("<I", 99))

    def test_byte_count_mismatch(self):
        arr = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        msg = _encode_event_graph("s", 1, 1, 1, True, [("x", arr)])
        # Find byte_count field: envelope(32) + prefix(8) + sname(7) + count(4) + ...
        # easier: just shorten the payload by 1 byte at the end
        msg_bad = msg[:-1]
        a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            a.sendall(msg_bad)
            a.close()
            with pytest.raises(EventGraphIPCError):
                receive_event_graph(b)
        finally:
            b.close()


# ---- tests: serve_one_connection integration -------------------------------

class TestServeOneConnection:
    def test_single_event_acked(self):
        """Full round-trip: sender → server → ACK → sender verifies ACK."""
        arr = np.arange(6, dtype=np.float32).reshape(2, 3)
        received_events: list[ReceivedEventGraph] = []
        eos_called: list[bool] = []

        import os, tempfile
        tmpdir = tempfile.mkdtemp()
        sock_path = os.path.join(tmpdir, "test.sock")

        server_sock = create_server_socket(sock_path)

        def run_server():
            def on_event(conn, ev):
                received_events.append(ev)
                send_ack(conn, ev.identity)
            def on_eos(identity):
                eos_called.append(True)
            serve_one_connection(server_sock, on_event, on_eos)
            server_sock.close()

        t = threading.Thread(target=run_server, daemon=True)
        t.start()

        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(sock_path)
        try:
            msg = _encode_event_graph("sample", 1, 2728, 1, True, [("x", arr)])
            client.sendall(msg)
            # Read ACK
            ack_raw = client.recv(32)
            assert len(ack_raw) == 32
            _, _, kind, _, _, _, _ = _ENV.unpack(ack_raw)
            assert kind == ACK
            # Send EOS
            client.sendall(_encode_eos(1, 2728, 1))
        finally:
            client.close()

        t.join(timeout=5.0)
        assert len(received_events) == 1
        assert received_events[0].sample_name == "sample"
        np.testing.assert_array_equal(received_events[0].arrays["x"], arr)
        assert len(eos_called) == 1
