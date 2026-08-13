"""SBNDIPC EventGraph receiver for the no-intermediate memory bridge.

Receives per-event EventGraph messages from TensorSetLabeler over a Unix-domain
socket and decodes them into ``dict[str, np.ndarray]`` — the same field-keyed
dict that ``adapt_tsl.read_tsl_event()`` returns from an HDF5 file.  The same
``build_apa_graph()`` function can then be used on either source without any
modification.

Wire format (all little-endian, defined in EventGraphIPC.h):

  Envelope (32 bytes):
    uint8[8]  magic       = b"SBNDIPC\\0"
    uint16    version     = 1
    uint16    msg_type    = 8 (EVENT_GRAPH) | 5 (ACK) | 6 (ERROR) | 7 (EOS)
    uint64    payload_len
    uint32    run, subrun, event

  EVENT_GRAPH payload (schema version 1):
    uint32    schema_version = 1
    uint32    flags          (bit 0 = has_truth)
    uint32    sample_name_len
    char[]    sample_name    (ASCII, no null terminator)
    uint32    member_count
    per member:
      uint32  name_len
      char[]  field_name    (e.g. "sp/pos")
      uint8   dtype         (1 = float32 LE, 2 = int64 LE)
      uint8   rank          (0 = scalar, 1 = 1D, 2 = 2D)
      uint16  reserved      = 0
      uint64  dims[rank]
      uint64  byte_count
      char[]  raw_bytes     (C-contiguous, little-endian)

  ACK:            envelope only (payload_len = 0)
  END_OF_STREAM:  envelope only (payload_len = 0)
"""

from __future__ import annotations

import io
import socket
import struct
from dataclasses import dataclass, field
from typing import Final

import numpy as np

# ---- protocol constants (mirror EventGraphIPC.h) ---------------------------

MAGIC: Final               = b"SBNDIPC\0"
PROTOCOL_VERSION: Final    = 1
EVENT_GRAPH: Final         = 8
ACK: Final                 = 5
ERROR: Final               = 6
END_OF_STREAM: Final       = 7
EVENT_GRAPH_SCHEMA_VERSION: Final = 1

DTYPE_FLOAT32_LE: Final    = 1
DTYPE_INT64_LE: Final      = 2

_DTYPE_MAP: Final = {
    DTYPE_FLOAT32_LE: np.dtype("<f4"),
    DTYPE_INT64_LE:   np.dtype("<i8"),
}

_ENV    = struct.Struct("<8sHHQIII")   # 32 bytes total
_U8     = struct.Struct("<B")
_U16    = struct.Struct("<H")
_U32    = struct.Struct("<I")
_U64    = struct.Struct("<Q")

# Payload size sanity limits
_MAX_PAYLOAD_BYTES  = 512 * 1024 * 1024  # 512 MB
_MAX_SAMPLE_NAME    = 256
_MAX_FIELD_NAME     = 128
_MAX_MEMBER_COUNT   = 200
_MAX_MEMBER_BYTES   = 400 * 1024 * 1024  # 400 MB


# ---- data classes ----------------------------------------------------------

@dataclass(frozen=True)
class EventGraphIdentity:
    run: int
    subrun: int
    event: int


@dataclass
class ReceivedEventGraph:
    identity: EventGraphIdentity
    sample_name: str
    has_truth: bool
    # dict[field_name -> ndarray]; exact keys match read_tsl_event() output
    arrays: dict = field(default_factory=dict)


class EventGraphIPCError(ValueError):
    """Malformed, inconsistent, or unexpected EventGraph IPC message."""


# ---- low-level I/O ---------------------------------------------------------

def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Read exactly n bytes from sock, retrying on EINTR."""
    buf = bytearray(n)
    view = memoryview(buf)
    received = 0
    while received < n:
        try:
            count = sock.recv_into(view[received:])
        except InterruptedError:
            continue
        if count == 0:
            raise EventGraphIPCError(f"peer closed after {received}/{n} bytes")
        received += count
    return bytes(buf)


def _read_u8(buf: io.BytesIO) -> int:
    return _U8.unpack(buf.read(1))[0]

def _read_u16(buf: io.BytesIO) -> int:
    return _U16.unpack(buf.read(2))[0]

def _read_u32(buf: io.BytesIO) -> int:
    return _U32.unpack(buf.read(4))[0]

def _read_u64(buf: io.BytesIO) -> int:
    return _U64.unpack(buf.read(8))[0]

def _read_str(buf: io.BytesIO, max_len: int, label: str) -> str:
    n = _read_u32(buf)
    if n > max_len:
        raise EventGraphIPCError(f"{label} length {n} exceeds limit {max_len}")
    raw = buf.read(n)
    if len(raw) != n:
        raise EventGraphIPCError(f"truncated {label}: expected {n}, got {len(raw)}")
    return raw.decode("ascii")


# ---- envelope helpers ------------------------------------------------------

def _read_envelope(sock: socket.socket):
    """Return (msg_type, identity, payload_len) from one envelope."""
    raw = _recv_exact(sock, _ENV.size)
    magic, version, msg_type, payload_len, run, sub, evt = _ENV.unpack(raw)
    if magic != MAGIC:
        raise EventGraphIPCError(f"bad magic {magic!r}")
    if version != PROTOCOL_VERSION:
        raise EventGraphIPCError(f"unsupported version {version}")
    return msg_type, EventGraphIdentity(int(run), int(sub), int(evt)), int(payload_len)


def _encode_ack(identity: EventGraphIdentity) -> bytes:
    return _ENV.pack(MAGIC, PROTOCOL_VERSION, ACK, 0,
                     identity.run, identity.subrun, identity.event)


def _encode_error(identity: EventGraphIdentity, msg: str) -> bytes:
    encoded = msg.encode("utf-8")[:4096]
    payload = _U32.pack(len(encoded)) + encoded
    env = _ENV.pack(MAGIC, PROTOCOL_VERSION, ERROR, len(payload),
                    identity.run, identity.subrun, identity.event)
    return env + payload


# ---- payload decoder -------------------------------------------------------

def _decode_event_graph_payload(
    payload: bytes, identity: EventGraphIdentity
) -> ReceivedEventGraph:
    """Parse raw EVENT_GRAPH payload bytes into a ReceivedEventGraph."""
    buf = io.BytesIO(payload)

    schema_ver = _read_u32(buf)
    if schema_ver != EVENT_GRAPH_SCHEMA_VERSION:
        raise EventGraphIPCError(f"unsupported schema version {schema_ver}")

    flags     = _read_u32(buf)
    has_truth = bool(flags & 1)

    sample_name  = _read_str(buf, _MAX_SAMPLE_NAME, "sample_name")
    member_count = _read_u32(buf)
    if member_count > _MAX_MEMBER_COUNT:
        raise EventGraphIPCError(f"member_count {member_count} > {_MAX_MEMBER_COUNT}")

    arrays: dict[str, np.ndarray] = {}
    for _ in range(member_count):
        fname      = _read_str(buf, _MAX_FIELD_NAME, "field_name")
        dtype_code = _read_u8(buf)
        rank       = _read_u8(buf)
        _read_u16(buf)  # reserved

        dtype = _DTYPE_MAP.get(dtype_code)
        if dtype is None:
            raise EventGraphIPCError(f"unknown dtype code {dtype_code} for '{fname}'")
        if rank > 2:
            raise EventGraphIPCError(f"rank {rank} > 2 for '{fname}'")

        dims = tuple(_read_u64(buf) for _ in range(rank))
        byte_count = _read_u64(buf)

        # Validate byte_count against expected element count * itemsize
        n_elements = 1
        for d in dims:
            n_elements *= d
        if rank == 0:
            n_elements = 1
        expected = n_elements * dtype.itemsize
        if byte_count != expected:
            raise EventGraphIPCError(
                f"byte_count {byte_count} != expected {expected} for '{fname}'"
            )
        if byte_count > _MAX_MEMBER_BYTES:
            raise EventGraphIPCError(
                f"member byte_count {byte_count} > {_MAX_MEMBER_BYTES} for '{fname}'"
            )

        raw = buf.read(byte_count)
        if len(raw) != byte_count:
            raise EventGraphIPCError(
                f"truncated data for '{fname}': expected {byte_count}, got {len(raw)}"
            )

        # Reconstruct as numpy array with exact dtype (no float32 -> float64 widening)
        arr = np.frombuffer(raw, dtype=dtype, count=n_elements).copy()
        if rank == 0:
            arr = arr.reshape(())
        elif rank == 1:
            arr = arr.reshape((dims[0],))
        else:
            arr = arr.reshape((dims[0], dims[1]))

        if fname in arrays:
            raise EventGraphIPCError(f"duplicate field '{fname}'")
        arrays[fname] = arr

    # Verify no trailing bytes in the payload
    remaining = len(payload) - buf.tell()
    if remaining:
        raise EventGraphIPCError(
            f"{remaining} unexpected trailing bytes in EVENT_GRAPH payload"
        )

    return ReceivedEventGraph(identity, sample_name, has_truth, arrays)


# ---- public API ------------------------------------------------------------

def receive_event_graph(sock: socket.socket) -> ReceivedEventGraph:
    """Receive one EVENT_GRAPH message.

    Reads the envelope, validates msg_type == EVENT_GRAPH, reads the payload,
    decodes into ReceivedEventGraph.  Does NOT send ACK — call send_ack()
    separately after consuming the data.

    Raises:
        EventGraphIPCError: on any protocol or format violation.
    """
    msg_type, identity, payload_len = _read_envelope(sock)
    if msg_type != EVENT_GRAPH:
        raise EventGraphIPCError(
            f"expected EVENT_GRAPH({EVENT_GRAPH}), got msg_type={msg_type}"
        )
    if payload_len > _MAX_PAYLOAD_BYTES:
        raise EventGraphIPCError(f"payload_len {payload_len} > {_MAX_PAYLOAD_BYTES}")

    payload = _recv_exact(sock, payload_len)
    return _decode_event_graph_payload(payload, identity)


def send_ack(sock: socket.socket, identity: EventGraphIdentity) -> None:
    """Send ACK for the given event identity."""
    sock.sendall(_encode_ack(identity))


def send_error(sock: socket.socket, identity: EventGraphIdentity, msg: str) -> None:
    """Send ERROR message (causes C++ wait_for_ack to return false)."""
    sock.sendall(_encode_error(identity, msg))


def serve_one_connection(
    server_sock: socket.socket,
    on_event,
    on_end_of_stream=None,
) -> None:
    """Accept one client connection and dispatch messages until END_OF_STREAM.

    ``on_event(conn, received)`` is called for each ReceivedEventGraph.
    It is responsible for calling send_ack() or send_error() before returning.

    ``on_end_of_stream(identity)`` is called when type-7 arrives (optional).
    """
    conn, _ = server_sock.accept()
    with conn:
        while True:
            msg_type, identity, payload_len = _read_envelope(conn)

            if msg_type == END_OF_STREAM:
                if on_end_of_stream is not None:
                    on_end_of_stream(identity)
                break

            if msg_type != EVENT_GRAPH:
                raise EventGraphIPCError(
                    f"expected EVENT_GRAPH or END_OF_STREAM, got {msg_type}"
                )
            if payload_len > _MAX_PAYLOAD_BYTES:
                raise EventGraphIPCError(f"payload_len {payload_len} too large")

            payload  = _recv_exact(conn, payload_len)
            received = _decode_event_graph_payload(payload, identity)
            on_event(conn, received)


def create_server_socket(path: str, backlog: int = 1) -> socket.socket:
    """Create a Unix-domain server socket at *path* and start listening."""
    import os
    # Remove stale socket file if present
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(path)
    sock.listen(backlog)
    return sock
