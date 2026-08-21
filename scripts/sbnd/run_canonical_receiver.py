#!/usr/bin/env python3
"""Canonical Memory-Writer receiver — multi-event persistent streaming.

Receives N EVENT_GRAPH messages from TensorSetLabeler over one OR MORE sequential
Unix-domain socket connections (one lar run per connection), appends each paired
physical event to a single StreamingH5Writer, then finalizes after all manifest
events have been received.

Multi-session mode (--max-sessions N or automatically when manifest has >1 row):
  One lar process per connection.  After each EOS the receiver keeps the H5
  writer open and waits for the next lar connection.  Finalize is called once
  after the connection that delivers the last expected event.

Per-event sequence:
  receive EVENT_GRAPH → decode → validate RSE against manifest → duplicate check
  → build_apa_graph(APA0) → build_apa_graph(APA1) → canonical gates
  → writer.append_event() → ACK

EOS sequence (single-session / last session):
  receive END_OF_STREAM → verify all expected events received → writer.finalize()

EOS sequence (non-final session in multi-session mode):
  receive END_OF_STREAM → events still pending → close connection → accept next

On any failure: writer.close() (leaves .partial for forensics), ERROR sent to C++.

Exit codes:
  0  PASS    — all events appended, finalize() succeeded
  1  GATE    — canonical gate failure (topology, conservation, shape)
  2  IPC     — protocol/socket error, RSE mismatch, or incomplete stream
  3  WRITER  — StreamingH5Writer.append_event() or finalize() failure
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import resource
import socket
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "clustering", "nugraph"))

# Fast IPC protocol imports — loaded before socket creation so PBS socket-ready
# detection fires in <2 s rather than waiting for the ~22 s torch cold start.
from pywcml.eventgraph_ipc import (
    END_OF_STREAM, EVENT_GRAPH,
    EventGraphIPCError, EventGraphIdentity,
    _ENV, _recv_exact, _decode_event_graph_payload,
    create_server_socket, send_ack, send_error,
    MAGIC, PROTOCOL_VERSION,
    _MAX_PAYLOAD_BYTES,
)

_TOPO_CTPC         = 1
_TOPO_KNN_FALLBACK = 2

CAMPAIGN_ID = "haiwang-nugraph4-canonical-v1"

# Sentinel returned by _run_event_loop when EOS is received but events are still
# missing.  Signals the outer multi-session loop to accept the next connection
# WITHOUT closing the H5 writer.  Never propagated to the shell exit code.
_EOS_INCOMPLETE = -10


class CanonicalGateError(RuntimeError):
    pass


def load_manifest(csv_path: str):
    """Return (set of (run,subrun,event), ordered list of row dicts)."""
    expected = set()
    rows = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            rse = (int(row["run"]), int(row["subrun"]), int(row["event"]))
            expected.add(rse)
            rows.append(row)
    return expected, rows


def _read_envelope(conn: socket.socket):
    raw = _recv_exact(conn, _ENV.size)
    magic, version, msg_type, payload_len, run, sub, evt = _ENV.unpack(raw)
    if magic != MAGIC:
        raise EventGraphIPCError(f"bad magic {magic!r}")
    if version != PROTOCOL_VERSION:
        raise EventGraphIPCError(f"unsupported protocol version {version}")
    return msg_type, EventGraphIdentity(int(run), int(sub), int(evt)), int(payload_len)


def _canonical_gates(arrays, g0, g1, ev_identity, gates):
    """Check all canonical conditions; raise CanonicalGateError on failure.

    Gates:
      1. topology_source == CTPC(1)
      2. sp/reco_bundle_id has no sentinel -1
      3. SP conservation: APA0 + APA1 == total
      4. Plane conservation for u, v, y
      5. Model-facing shapes: sp.features (N,2), plane.x (M,5)
      6. Deterministic split is a valid label
    """
    topo_src = int(np.array(arrays.get("metadata/sp_topology_source", [0])).flat[0])
    if topo_src != _TOPO_CTPC:
        raise CanonicalGateError(f"topology_source={topo_src} not CTPC={_TOPO_CTPC}")
    gates["topology_source"] = topo_src

    sp_reco_bund = arrays["sp/reco_bundle_id"].flatten().astype(np.int64)
    n_sentinel = int(np.sum(sp_reco_bund == -1))
    if n_sentinel:
        raise CanonicalGateError(f"sp/reco_bundle_id has {n_sentinel} sentinel (-1) values")
    gates["reco_bundle_id_sentinels"] = 0

    sp_apa = arrays["sp/apa"].flatten().astype(np.int64)
    n_sp_total = len(sp_apa)
    n_sp_0 = int(np.sum(sp_apa == 0))
    n_sp_1 = int(np.sum(sp_apa == 1))
    if n_sp_0 + n_sp_1 != n_sp_total:
        raise CanonicalGateError(
            f"SP conservation: APA0({n_sp_0})+APA1({n_sp_1}) != total({n_sp_total})"
        )
    gates["sp_conservation"] = {"total": n_sp_total, "apa0": n_sp_0, "apa1": n_sp_1}

    for pname in ("u", "v", "y"):
        p_apa = arrays[f"{pname}/apa"].flatten().astype(np.int64)
        n_total = len(p_apa)
        n0 = int(np.sum(p_apa == 0))
        n1 = int(np.sum(p_apa == 1))
        if n0 + n1 != n_total:
            raise CanonicalGateError(
                f"{pname} plane conservation: APA0({n0})+APA1({n1}) != total({n_total})"
            )
    gates["plane_conservation"] = "OK"

    for apa_idx, g in ((0, g0), (1, g1)):
        sf = tuple(g["sp"].features.shape)
        if len(sf) < 2 or sf[1] != 2:
            raise CanonicalGateError(f"APA{apa_idx} sp.features.shape={sf}, expected (N,2)")
        for pname in ("u", "v", "y"):
            xf = tuple(g[pname].x.shape)
            if len(xf) < 2 or xf[1] != 5:
                raise CanonicalGateError(f"APA{apa_idx} {pname}.x.shape={xf}, expected (M,5)")
    gates["model_facing_shapes"] = "OK"

    split = ev_identity.split()
    if split not in ("train", "validation", "test"):
        raise CanonicalGateError(f"unrecognized split: {split!r}")
    gates["split"] = split


def _run_event_loop(
    conn,
    expected_rses,
    output_h5,
    campaign_id,
    build_fn,
    topology_error_cls,
    event_identity_cls,
    writer_cls,
    report,
    report_path=None,
    writer=None,
    received_rses=None,
    event_reports=None,
):
    """Core multi-event persistent loop for one connection.

    Injectable dependencies allow unit-testing without the ML stack.
    When writer/received_rses/event_reports are provided they persist across
    multiple calls (multi-session mode); otherwise fresh state is created.

    Returns:
      0              PASS (all expected events received + writer finalized)
      1              GATE canonical gate failure
      2              IPC protocol / RSE mismatch / stream error
      3              WRITER finalize/append failure
      _EOS_INCOMPLETE EOS received but events still pending; writer left open
    """
    if received_rses is None:
        received_rses = set()
    if event_reports is None:
        event_reports = []
    if writer is None:
        writer = writer_cls(output_h5)

    def _abort(exit_code, **fields):
        writer.close()
        report.update(
            events_received=len(received_rses),
            events=event_reports,
            **fields,
        )
        _write_report(report, report_path)
        return exit_code

    try:
        while True:
            msg_type, ipc_id, payload_len = _read_envelope(conn)
            run, subrun, event = ipc_id.run, ipc_id.subrun, ipc_id.event

            # ── END_OF_STREAM ────────────────────────────────────────────────
            if msg_type == END_OF_STREAM:
                missing = expected_rses - received_rses
                if missing:
                    # Multi-session: this connection's lar job is done but more
                    # events are still expected from subsequent lar connections.
                    # Do NOT close the writer — return sentinel so the outer loop
                    # accepts the next connection.
                    miss_list = sorted(missing)
                    print(
                        f"[receiver] EOS_INCOMPLETE — {len(missing)} events still "
                        f"pending after this session: {miss_list}",
                        flush=True,
                    )
                    _write_report(report | {
                        "status": "IN_PROGRESS",
                        "events_received": len(received_rses),
                        "events": event_reports,
                    }, report_path)
                    return _EOS_INCOMPLETE

                try:
                    writer.finalize()
                except Exception as exc:
                    err = f"finalize failed: {exc}"
                    print(f"[receiver] WRITER_FAIL: {err}", flush=True)
                    return _abort(3, status="WRITER_FAIL", error=err)

                report.update(
                    status="PASS",
                    events_received=len(received_rses),
                    events=event_reports,
                )
                _write_report(report, report_path)
                print(
                    f"[receiver] PASS — {len(received_rses)} events, output: {output_h5}",
                    flush=True,
                )
                return 0

            # ── EVENT_GRAPH ──────────────────────────────────────────────────
            if msg_type != EVENT_GRAPH:
                err = f"unexpected msg_type={msg_type}, expected EVENT_GRAPH or EOS"
                send_error(conn, ipc_id, err)
                return _abort(2, status="ERROR", error=err)

            rse = (run, subrun, event)

            if rse in received_rses:
                err = f"duplicate RSE ({run},{subrun},{event})"
                send_error(conn, ipc_id, err)
                return _abort(2, status="ERROR", error=err)

            if expected_rses and rse not in expected_rses:
                err = f"unexpected RSE ({run},{subrun},{event}) not in manifest"
                send_error(conn, ipc_id, err)
                return _abort(2, status="ERROR", error=err)

            if payload_len > _MAX_PAYLOAD_BYTES:
                err = f"payload_len {payload_len} exceeds limit {_MAX_PAYLOAD_BYTES}"
                send_error(conn, ipc_id, err)
                return _abort(2, status="ERROR", error=err)

            payload  = _recv_exact(conn, payload_len)
            received = _decode_event_graph_payload(payload, ipc_id)
            arrays   = received.arrays

            print(
                f"[receiver] EVENT_GRAPH rse=({run},{subrun},{event}) "
                f"payload={payload_len} fields={len(arrays)} "
                f"sample={received.sample_name}",
                flush=True,
            )

            # ── Build per-APA graphs ────────────────────────────────────────
            try:
                g0 = build_fn(arrays, 0, run, subrun, event, topology_gate=True)
                g1 = build_fn(arrays, 1, run, subrun, event, topology_gate=True)
            except topology_error_cls as exc:
                err = f"topology gate rejected ({run},{subrun},{event}): {exc}"
                send_error(conn, ipc_id, err)
                event_reports.append({
                    "run": run, "subrun": subrun, "event": event,
                    "status": "GATE_FAIL", "error": err,
                })
                return _abort(1, status="GATE_FAIL", error=err)

            nsp0 = int(g0["sp"].pos.shape[0])
            nsp1 = int(g1["sp"].pos.shape[0])
            print(
                f"[receiver] APA graphs built rse=({run},{subrun},{event}) "
                f"APA0_sp={nsp0} APA1_sp={nsp1}",
                flush=True,
            )

            # ── Canonical gates ─────────────────────────────────────────────
            ev_identity = event_identity_cls(
                campaign_id=campaign_id,
                shard_id=0,
                source_index=0,
                run=run,
                subrun=subrun,
                event=event,
                random_seed=0,
            )
            gates = {}
            try:
                _canonical_gates(arrays, g0, g1, ev_identity, gates)
            except CanonicalGateError as exc:
                err = f"canonical gate ({run},{subrun},{event}): {exc}"
                send_error(conn, ipc_id, err)
                event_reports.append({
                    "run": run, "subrun": subrun, "event": event,
                    "status": "GATE_FAIL", "error": err, "gates": gates,
                })
                return _abort(1, status="GATE_FAIL", error=err)

            print(
                f"[receiver] gates PASS rse=({run},{subrun},{event}) "
                f"split={gates.get('split')} topo={gates.get('topology_source')}",
                flush=True,
            )

            # ── Append to writer ────────────────────────────────────────────
            try:
                name0, name1 = writer.append_event(ev_identity, g0, g1)
            except Exception as exc:
                err = f"writer.append_event ({run},{subrun},{event}): {exc}"
                send_error(conn, ipc_id, err)
                event_reports.append({
                    "run": run, "subrun": subrun, "event": event,
                    "status": "WRITER_FAIL", "error": err,
                })
                return _abort(3, status="WRITER_FAIL", error=err)

            received_rses.add(rse)
            rss_kib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

            # ── ACK only after successful append ────────────────────────────
            send_ack(conn, ipc_id)
            print(
                f"[receiver] ACK rse=({run},{subrun},{event}) "
                f"samples=({name0},{name1}) rss={rss_kib}kB",
                flush=True,
            )

            ev_rpt = {
                "run": run, "subrun": subrun, "event": event,
                "status": "PASS",
                "nsp_apa0": nsp0, "nsp_apa1": nsp1,
                "sample_name_apa0": name0,
                "sample_name_apa1": name1,
                "split": gates.get("split"),
                "rss_kib": rss_kib,
                "gates": gates,
            }
            event_reports.append(ev_rpt)
            _write_report(report | {
                "status": "IN_PROGRESS",
                "events_received": len(received_rses),
                "events": event_reports,
            }, report_path)

    except EventGraphIPCError as exc:
        err = f"IPC error: {exc}"
        print(f"[receiver] IPC ERROR: {err}", flush=True)
        return _abort(2, status="ERROR", error=err)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Canonical Memory-Writer receiver (multi-event persistent, multi-session)"
    )
    parser.add_argument("--socket", required=True,
                        help="Unix-domain socket path")
    parser.add_argument("--output-h5", required=True,
                        help="Canonical output H5 path")
    parser.add_argument("--expected-manifest", required=True,
                        help="CSV manifest listing expected (run,subrun,event) rows")
    parser.add_argument("--report", default="canonical_receiver_report.json",
                        help="JSON report output path")
    parser.add_argument("--timeout", type=float, default=180.0,
                        help="Seconds to wait for FIRST connection")
    parser.add_argument("--inter-session-timeout", type=float, default=900.0,
                        help="Seconds to wait for each SUBSEQUENT connection (default 900)")
    parser.add_argument("--max-sessions", type=int, default=0,
                        help="Max lar connections to accept (default = manifest row count)")
    args = parser.parse_args()

    expected_rses, manifest_rows = load_manifest(args.expected_manifest)
    max_sessions = args.max_sessions if args.max_sessions > 0 else len(manifest_rows)

    report = {
        "socket":            args.socket,
        "output_h5":         args.output_h5,
        "manifest":          args.expected_manifest,
        "status":            "PENDING",
        "timestamp":         time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "campaign_id":       CAMPAIGN_ID,
        "events_expected":   len(expected_rses),
        "max_sessions":      max_sessions,
        "expected_rses":     [list(rse) for rse in sorted(expected_rses)],
    }

    # ── Create socket FIRST ────────────────────────────────────────────────────
    try:
        server_sock = create_server_socket(args.socket)
    except OSError as exc:
        report.update(status="ERROR", error=f"socket create failed: {exc}")
        _write_report(report, args.report)
        return 2

    print(f"[receiver] listening on {args.socket}", flush=True)
    print(
        f"[receiver] expecting {len(expected_rses)} events over up to {max_sessions} sessions",
        flush=True,
    )

    # ── Heavy deferred ML imports ──────────────────────────────────────────────
    from pywcml.adapt_tsl import build_apa_graph, TopologyGateError
    from pywcml.identity import EventIdentity
    from pywcml.h5writer import StreamingH5Writer
    print("[receiver] ML imports loaded", flush=True)

    # ── Create persistent state shared across all sessions ─────────────────────
    writer        = StreamingH5Writer(args.output_h5)
    received_rses = set()
    event_reports = []

    exit_code = 2  # default = IPC error if loop exits without PASS
    for session_idx in range(max_sessions):
        timeout = args.timeout if session_idx == 0 else args.inter_session_timeout
        server_sock.settimeout(timeout)

        try:
            conn, _ = server_sock.accept()
        except socket.timeout:
            err = (
                f"no connection for session {session_idx + 1}/{max_sessions} "
                f"within {timeout}s"
            )
            print(f"[receiver] TIMEOUT: {err}", flush=True)
            writer.close()
            report.update(status="ERROR", error=err)
            _write_report(report, args.report)
            server_sock.close()
            return 2

        print(
            f"[receiver] session {session_idx + 1}/{max_sessions} connected "
            f"({len(received_rses)}/{len(expected_rses)} events so far)",
            flush=True,
        )

        with conn:
            exit_code = _run_event_loop(
                conn,
                expected_rses=expected_rses,
                output_h5=args.output_h5,
                campaign_id=CAMPAIGN_ID,
                build_fn=build_apa_graph,
                topology_error_cls=TopologyGateError,
                event_identity_cls=EventIdentity,
                writer_cls=StreamingH5Writer,
                report=report,
                report_path=args.report,
                writer=writer,
                received_rses=received_rses,
                event_reports=event_reports,
            )

        if exit_code == 0:
            # All events received and H5 finalized — PASS.
            break
        if exit_code == _EOS_INCOMPLETE:
            # This session finished but more events still expected.
            print(
                f"[receiver] session {session_idx + 1} done "
                f"({len(received_rses)}/{len(expected_rses)} received), "
                f"waiting for next session…",
                flush=True,
            )
            continue
        # Any other code (1=GATE, 2=IPC, 3=WRITER) is a real error.
        # _abort() inside _run_event_loop already closed the writer.
        break
    else:
        # Exhausted max_sessions without PASS or fatal error.
        missing = expected_rses - received_rses
        err = (
            f"exhausted {max_sessions} sessions with "
            f"{len(missing)} events still missing: {sorted(missing)}"
        )
        print(f"[receiver] INCOMPLETE: {err}", flush=True)
        writer.close()
        report.update(status="INCOMPLETE", error=err)
        _write_report(report, args.report)
        exit_code = 2

    server_sock.close()
    return 0 if exit_code == 0 else exit_code


def _write_report(report, path):
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"[receiver] report written: {path}", flush=True)
    except OSError as exc:
        print(f"[receiver] WARNING: could not write report: {exc}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
