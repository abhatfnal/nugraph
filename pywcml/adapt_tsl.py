"""Adapter: TensorSetLabeler all-APA H5 → canonical per-APA NuGraph samples.

Public API
----------
read_tsl_event(h5path, sample_name=None) -> (arrays, sample_name)
build_apa_graph(arrays, apa)             -> NuGraphData
adapt_tsl_to_canonical(...)              -> Path

Design goal
-----------
Transformation logic is PURE: arrays/event → APA-specific NuGraphData.
File I/O is a thin wrapper around the pure core.  The same ``build_apa_graph``
can be called with in-memory arrays from a future transport layer with no
semantic changes.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Optional

import h5py
import numpy as np
import torch

from pynuml.data import NuGraphData

from .geometry import triangulation_edges
from .h5writer import StreamingH5Writer
from .identity import EventIdentity

# Plane names in canonical order
PLANE_NAMES: tuple[str, ...] = ("u", "v", "y")

# Topology source enum (must match TensorSetLabeler.cxx)
TOPO_CTPC = 1
TOPO_KNN_FALLBACK = 2
_TOPO_NAMES = {TOPO_CTPC: "CTPC", TOPO_KNN_FALLBACK: "KNN_FALLBACK"}

# Field backward-compat invariant: sp/features[:,1].astype(int64) == sp/reco_segment_id
_FEAT_COL_CHARGE = 0
_FEAT_COL_RECO_SEG = 1


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class EdgeAccountingEntry:
    """Edge counts for one edge family after APA partitioning."""
    field: str
    source_count: int
    apa0_retained: int
    apa1_retained: int
    cross_apa_discarded: int

    def check_conservation(self) -> bool:
        return (
            self.source_count
            == self.apa0_retained + self.apa1_retained + self.cross_apa_discarded
        )


@dataclasses.dataclass
class AdaptationResult:
    """All outputs and accounting from one physical-event adaptation."""
    run: int
    subrun: int
    event: int
    topology_source: int
    topology_name: str
    nsp_source: int
    nsp_apa0: int
    nsp_apa1: int
    plane_counts_source: dict  # {plane: int}
    plane_counts_apa0: dict
    plane_counts_apa1: dict
    edge_accounting: list[EdgeAccountingEntry]
    delaunay_counts_apa0: dict   # {plane: int}
    delaunay_counts_apa1: dict
    graph_apa0: NuGraphData
    graph_apa1: NuGraphData
    sample_name_apa0: str
    sample_name_apa1: str


# ---------------------------------------------------------------------------
# I/O layer
# ---------------------------------------------------------------------------

def read_tsl_event(
    h5path: str | Path,
    sample_name: Optional[str] = None,
) -> tuple[dict, str]:
    """Read one event from a TensorSetLabeler-format HDF5 file.

    Returns
    -------
    arrays : dict mapping HDF5 field name -> numpy array
    sample_name : str
    """
    with h5py.File(h5path, "r") as f:
        if sample_name is None:
            names = list(f["dataset"].keys())
            if not names:
                raise ValueError(f"no samples in {h5path}")
            sample_name = names[0]
        ev = f["dataset"][sample_name][()]
    arrays = {name: np.array(ev[name]) for name in ev.dtype.names}
    return arrays, sample_name


def _load_edge_index(arrays: dict, field: str) -> np.ndarray:
    """Return edge index as (2, E) int64, unwrapping TSL dummy (single (0,0))."""
    arr = arrays[field].reshape(2, -1).astype(np.int64)
    # TSL writes a dummy [[0],[0]] when no real edges exist.  SP-SP edges never
    # have self-loops; nexus edges (plane=0,sp=0) are theoretically valid but
    # the single-entry dummy is only used when the entire edge list is empty.
    if arr.shape[1] == 1 and int(arr[0, 0]) == 0 and int(arr[1, 0]) == 0:
        return np.empty((2, 0), dtype=np.int64)
    return arr


def _sorted_edge_pairs(ei: np.ndarray) -> np.ndarray:
    """Return (2, E) edge index with columns lexicographically sorted."""
    if ei.shape[1] == 0:
        return ei
    pairs = np.stack([ei[0], ei[1]], axis=1)  # (E, 2)
    order = np.lexsort((pairs[:, 1], pairs[:, 0]))
    return pairs[order].T.astype(np.int64)


# ---------------------------------------------------------------------------
# Pure core: APA partition + graph construction
# ---------------------------------------------------------------------------

def build_apa_graph(
    arrays: dict,
    apa: int,
    run: int,
    subrun: int,
    event: int,
    *,
    topology_gate: bool = True,
) -> NuGraphData:
    """Build a per-APA NuGraphData from a TSL all-APA event array dict.

    Parameters
    ----------
    arrays
        Output of ``read_tsl_event``.
    apa
        0 or 1.
    run, subrun, event
        Physical event identity (read from ``metadata/*`` fields in arrays).
    topology_gate
        If True, raise ``TopologyGateError`` when topology_source == KNN_FALLBACK.

    Returns
    -------
    NuGraphData for the requested APA.
    """
    if apa not in (0, 1):
        raise ValueError(f"apa must be 0 or 1, got {apa!r}")

    # ---- topology gate ----
    topo_src = int(np.array(arrays.get("metadata/sp_topology_source", [0])).flat[0])
    if topology_gate and topo_src == TOPO_KNN_FALLBACK:
        raise TopologyGateError(
            f"event (run={run} sub={subrun} evt={event}) has "
            f"KNN_FALLBACK topology; refusing to write to canonical dataset"
        )

    # ---- SP partition ----
    sp_apa = arrays["sp/apa"].flatten().astype(np.int64)
    sp_mask = sp_apa == apa
    old_sp_idx = np.where(sp_mask)[0]
    Napa = len(old_sp_idx)

    sp_old_to_new = np.full(len(sp_apa), -1, dtype=np.int64)
    sp_old_to_new[old_sp_idx] = np.arange(Napa, dtype=np.int64)

    # Slice SP arrays
    sp_pos     = arrays["sp/pos"].reshape(-1, 3)[old_sp_idx].astype(np.float32)
    sp_feat6   = arrays["sp/features"].reshape(-1, 6)[old_sp_idx].astype(np.float32)
    sp_reco_seg  = arrays["sp/reco_segment_id"].flatten()[old_sp_idx].astype(np.int64)
    sp_reco_bund = arrays["sp/reco_bundle_id"].flatten()[old_sp_idx].astype(np.int64)
    sp_y_sem   = arrays["sp/y_semantic"].flatten()[old_sp_idx].astype(np.int64)
    sp_y_inst  = arrays["sp/y_instance"].flatten()[old_sp_idx].astype(np.int64)
    sp_rawvtx  = arrays["sp/raw_vtx_dist"].flatten()[old_sp_idx].astype(np.float32)

    # Verify backward-compat invariant before stripping truth columns
    feat_col1_as_int = sp_feat6[:, _FEAT_COL_RECO_SEG].astype(np.int64)
    if not np.all(feat_col1_as_int == sp_reco_seg):
        bad = int(np.sum(feat_col1_as_int != sp_reco_seg))
        raise AssertionError(
            f"APA{apa}: sp/features[:,1].astype(int64) != reco_segment_id at {bad} SPs"
        )

    # Model-facing sp/features: (N, 2) reco-only
    sp_features = np.stack(
        [sp_feat6[:, _FEAT_COL_CHARGE], sp_reco_seg.astype(np.float32)],
        axis=1,
    ).astype(np.float32)

    # ---- SP-SP edges (nexus + supervision share same topology) ----
    sp_sp_ei  = _load_edge_index(arrays, "sp_nexus_sp/edge_index")
    sp_el_ei  = _load_edge_index(arrays, "sp/edge_label_index")
    sp_ey_all = arrays["sp/edge_y"].flatten().astype(np.int64)
    sp_el_all = arrays["sp/edge_labelable"].flatten().astype(np.int64)

    sp_nexus_apa, _  = _filter_sp_sp(sp_sp_ei, sp_apa, apa, sp_old_to_new)
    sp_label_apa, sp_ey_apa, sp_el_apa = _filter_sp_sp_supervised(
        sp_el_ei, sp_ey_all, sp_el_all, sp_apa, apa, sp_old_to_new
    )

    # ---- Per-plane partition ----
    plane_stores: dict[str, dict] = {}
    for pname in PLANE_NAMES:
        plane_stores[pname] = _build_plane_store(
            arrays, pname, apa, sp_apa, sp_old_to_new
        )

    # ---- Build NuGraphData ----
    graph = NuGraphData()
    graph["metadata"].run     = int(run)
    graph["metadata"].subrun  = int(subrun)
    graph["metadata"].event   = int(event)
    if topo_src:
        graph["metadata"].sp_topology_source = int(topo_src)

    # SP nodes
    graph["sp"].pos            = torch.as_tensor(sp_pos, dtype=torch.float32)
    graph["sp"].features       = torch.as_tensor(sp_features, dtype=torch.float32)
    graph["sp"].y_semantic     = torch.as_tensor(sp_y_sem, dtype=torch.long)
    graph["sp"].y_instance     = torch.as_tensor(sp_y_inst, dtype=torch.long)
    graph["sp"].raw_vtx_dist   = torch.as_tensor(sp_rawvtx, dtype=torch.float32)
    graph["sp"].reco_bundle_id  = torch.as_tensor(sp_reco_bund, dtype=torch.long)
    graph["sp"].reco_segment_id = torch.as_tensor(sp_reco_seg, dtype=torch.long)

    # SP supervision (stored on the sp node store; Dataset.get() moves to edge store)
    graph["sp"].edge_label_index = torch.as_tensor(sp_label_apa, dtype=torch.long)
    graph["sp"].edge_y           = torch.as_tensor(sp_ey_apa, dtype=torch.long)
    graph["sp"].edge_labelable   = torch.as_tensor(sp_el_apa, dtype=torch.long)

    # SP nexus (message-passing) edges
    graph["sp", "nexus", "sp"].edge_index = torch.as_tensor(sp_nexus_apa, dtype=torch.long)

    # Plane nodes
    for pname in PLANE_NAMES:
        ps = plane_stores[pname]
        graph[pname].pos         = torch.as_tensor(ps["pos"],        dtype=torch.float32)
        graph[pname].x           = torch.as_tensor(ps["x"],          dtype=torch.float32)
        graph[pname].id          = torch.as_tensor(ps["id"],         dtype=torch.long)
        graph[pname].y_semantic  = torch.as_tensor(ps["y_semantic"], dtype=torch.long)
        graph[pname].y_instance  = torch.as_tensor(ps["y_instance"], dtype=torch.long)
        graph[pname, "plane", pname].edge_index = torch.as_tensor(ps["plane_edges"], dtype=torch.long)
        graph[pname, "nexus", "sp"].edge_index  = torch.as_tensor(ps["nexus"],       dtype=torch.long)

    # Event level
    graph["evt"].num_nodes = 1
    # evt/y: preserve event-level truth from TSL (same for both APAs)
    evt_y = int(np.array(arrays.get("evt/y", [0])).flat[0])
    graph["evt"].y = torch.tensor([evt_y], dtype=torch.long)

    return graph


def _filter_sp_sp(
    ei: np.ndarray,
    sp_apa: np.ndarray,
    apa: int,
    old_to_new: np.ndarray,
) -> tuple[np.ndarray, int]:
    """Filter SP-SP edges to a single APA and remap indices.

    Returns (remapped_ei, n_cross_discarded).
    """
    if ei.shape[1] == 0:
        return np.empty((2, 0), dtype=np.int64), 0
    src, dst = ei[0], ei[1]
    src_apa = sp_apa[src]
    dst_apa = sp_apa[dst]
    same_apa = (src_apa == apa) & (dst_apa == apa)
    cross = int(np.sum((src_apa != dst_apa)))
    if not np.any(same_apa):
        return np.empty((2, 0), dtype=np.int64), cross
    remapped = np.stack(
        [old_to_new[src[same_apa]], old_to_new[dst[same_apa]]], axis=0
    )
    return remapped, cross


def _filter_sp_sp_supervised(
    ei: np.ndarray,
    edge_y: np.ndarray,
    edge_labelable: np.ndarray,
    sp_apa: np.ndarray,
    apa: int,
    old_to_new: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Filter SP supervision edges to one APA, remap, return aligned labels."""
    if ei.shape[1] == 0:
        # dummy already cleared → inject minimal dummy for HDF5 compatibility
        return (
            np.array([[0], [0]], dtype=np.int64),
            np.array([0], dtype=np.int64),
            np.array([0], dtype=np.int64),
        )
    src, dst = ei[0], ei[1]
    mask = (sp_apa[src] == apa) & (sp_apa[dst] == apa)
    if not np.any(mask):
        return (
            np.array([[0], [0]], dtype=np.int64),
            np.array([0], dtype=np.int64),
            np.array([0], dtype=np.int64),
        )
    remapped = np.stack(
        [old_to_new[src[mask]], old_to_new[dst[mask]]], axis=0
    )
    # Handle edge_y/edge_labelable: they may be the dummy [0] when ei is real
    # TSL dummy supervision: ss empty → {0,0} single edge with ey=[0], el=[0].
    # If we got here, ei.shape[1] > 0, but edge_y may still be length 1 (dummy).
    n_src = int(ei.shape[1])
    if edge_y.shape[0] == n_src:
        ey_out = edge_y[mask].astype(np.int64)
        el_out = edge_labelable[mask].astype(np.int64)
    else:
        # Mismatch — shouldn't happen with well-formed TSL output, but guard
        ey_out = np.zeros(int(mask.sum()), dtype=np.int64)
        el_out = np.zeros(int(mask.sum()), dtype=np.int64)
    return remapped, ey_out, el_out


def _build_plane_store(
    arrays: dict,
    pname: str,
    apa: int,
    sp_apa: np.ndarray,
    sp_old_to_new: np.ndarray,
) -> dict:
    """Build one plane's per-APA store dict."""
    p_apa_arr = arrays[f"{pname}/apa"].flatten().astype(np.int64)
    p_mask = p_apa_arr == apa
    old_p_idx = np.where(p_mask)[0]
    Mapa = len(old_p_idx)

    p_old_to_new = np.full(len(p_apa_arr), -1, dtype=np.int64)
    p_old_to_new[old_p_idx] = np.arange(Mapa, dtype=np.int64)

    pos = arrays[f"{pname}/pos"].reshape(-1, 2)[old_p_idx].astype(np.float32)
    x15 = arrays[f"{pname}/x"].reshape(-1, 15)[old_p_idx]
    # Design decision: 5 reco-only columns (no MCTruth vertex quantities)
    x5 = x15[:, :5].astype(np.float32)
    pid = np.arange(Mapa, dtype=np.int64)
    y_sem = arrays[f"{pname}/y_semantic"].flatten()[old_p_idx].astype(np.int64)
    y_inst = arrays[f"{pname}/y_instance"].flatten()[old_p_idx].astype(np.int64)

    # Intra-plane Delaunay edges (new: not in TSL H5)
    if Mapa >= 2:
        plane_edges = triangulation_edges(pos)
    else:
        plane_edges = np.empty((2, 0), dtype=np.int64)
    # Lexicographic sort for deterministic bytes
    plane_edges = _sorted_edge_pairs(plane_edges)

    # Nexus edges (plane→SP): filter by APA
    nex_ei = _load_edge_index(arrays, f"{pname}_nexus_sp/edge_index")

    if nex_ei.shape[1] == 0:
        nexus_apa = np.empty((2, 0), dtype=np.int64)
    else:
        p_src, sp_dst = nex_ei[0], nex_ei[1]

        # Assert TSL nexus APA/face invariant (plane APA == SP APA for all edges)
        p_apa_of_edge = p_apa_arr[p_src]
        s_apa_of_edge = sp_apa[sp_dst]
        n_mismatch = int(np.sum(p_apa_of_edge != s_apa_of_edge))
        if n_mismatch:
            raise AssertionError(
                f"{pname}_nexus_sp: {n_mismatch} edges violate "
                f"TSL APA invariant (plane_apa != sp_apa)"
            )

        keep = p_mask[p_src] & (sp_apa[sp_dst] == apa)
        if np.any(keep):
            p_new  = p_old_to_new[p_src[keep]]
            sp_new = sp_old_to_new[sp_dst[keep]]
            nexus_apa = np.stack([p_new, sp_new], axis=0)
        else:
            nexus_apa = np.empty((2, 0), dtype=np.int64)

    return {
        "pos": pos,
        "x": x5,
        "id": pid,
        "y_semantic": y_sem,
        "y_instance": y_inst,
        "plane_edges": plane_edges,
        "nexus": nexus_apa,
        "n_plane_old": len(p_apa_arr),
        "n_plane_apa": Mapa,
    }


# ---------------------------------------------------------------------------
# End-to-end adapter
# ---------------------------------------------------------------------------

class TopologyGateError(RuntimeError):
    """Raised when an event has KNN_FALLBACK topology."""


def adapt_tsl_to_canonical(
    tsl_h5_path: str | Path,
    output_h5_path: str | Path,
    *,
    campaign_id: str,
    shard_id: int = 0,
    source_index: int = 0,
    random_seed: int = 0,
    sample_name: Optional[str] = None,
    topology_gate: bool = True,
) -> AdaptationResult:
    """Adapt one TensorSetLabeler H5 event to the canonical streaming format.

    Reads the all-APA TSL record, partitions into APA0/APA1, and writes both
    to a StreamingH5Writer-managed canonical H5 file.

    Parameters
    ----------
    tsl_h5_path
        Path to the TSL-format HDF5 (e.g. nugraph.h5 from validation run).
    output_h5_path
        Destination canonical H5 (must not exist yet).
    campaign_id
        Training campaign identifier (used for BLAKE2b split assignment).
    shard_id, source_index, random_seed
        EventIdentity fields (shard=0, source=0, seed=0 for prototype).
    sample_name
        TSL sample name; first sample if None.
    topology_gate
        If True, reject events with KNN_FALLBACK topology.

    Returns
    -------
    AdaptationResult with full accounting.
    """
    arrays, tsl_sample = read_tsl_event(tsl_h5_path, sample_name)

    run    = int(np.array(arrays["metadata/run"]).flat[0])
    subrun = int(np.array(arrays["metadata/subrun"]).flat[0])
    event  = int(np.array(arrays["metadata/event"]).flat[0])

    topo_src = int(np.array(arrays.get("metadata/sp_topology_source", [0])).flat[0])
    if topology_gate and topo_src == TOPO_KNN_FALLBACK:
        raise TopologyGateError(
            f"R={run}/SR={subrun}/E={event}: topology_source=KNN_FALLBACK; "
            "not writing to canonical dataset"
        )

    # ---- Accounting: source counts ----
    sp_apa_all = arrays["sp/apa"].flatten().astype(np.int64)
    nsp_source = len(sp_apa_all)
    nsp_apa = {a: int(np.sum(sp_apa_all == a)) for a in (0, 1)}

    plane_counts_source: dict[str, int] = {}
    plane_counts_apa: dict[int, dict[str, int]] = {0: {}, 1: {}}
    for pname in PLANE_NAMES:
        p_apa_all = arrays[f"{pname}/apa"].flatten().astype(np.int64)
        plane_counts_source[pname] = len(p_apa_all)
        for a in (0, 1):
            plane_counts_apa[a][pname] = int(np.sum(p_apa_all == a))

    # ---- Build per-APA graphs ----
    graph_apa0 = build_apa_graph(arrays, 0, run, subrun, event, topology_gate=topology_gate)
    graph_apa1 = build_apa_graph(arrays, 1, run, subrun, event, topology_gate=topology_gate)

    # ---- Edge accounting ----
    edge_accounting = _compute_edge_accounting(arrays, sp_apa_all, graph_apa0, graph_apa1)

    # ---- Delaunay edge counts (adapter-derived, no source comparison) ----
    delaunay_counts: dict[int, dict[str, int]] = {}
    for a, g in ((0, graph_apa0), (1, graph_apa1)):
        delaunay_counts[a] = {}
        for pname in PLANE_NAMES:
            try:
                ei = g[pname, "plane", pname].edge_index
                delaunay_counts[a][pname] = int(ei.shape[1]) if ei.dim() == 2 else 0
            except (KeyError, AttributeError):
                delaunay_counts[a][pname] = 0

    # ---- Write via StreamingH5Writer ----
    identity = EventIdentity(
        campaign_id=campaign_id,
        shard_id=shard_id,
        source_index=source_index,
        run=run,
        subrun=subrun,
        event=event,
        random_seed=random_seed,
    )

    output_h5_path = Path(output_h5_path)
    with StreamingH5Writer(output_h5_path) as writer:
        name0, name1 = writer.append_event(identity, graph_apa0, graph_apa1)

    return AdaptationResult(
        run=run,
        subrun=subrun,
        event=event,
        topology_source=topo_src,
        topology_name=_TOPO_NAMES.get(topo_src, f"UNKNOWN({topo_src})"),
        nsp_source=nsp_source,
        nsp_apa0=nsp_apa[0],
        nsp_apa1=nsp_apa[1],
        plane_counts_source=plane_counts_source,
        plane_counts_apa0=plane_counts_apa[0],
        plane_counts_apa1=plane_counts_apa[1],
        edge_accounting=edge_accounting,
        delaunay_counts_apa0=delaunay_counts[0],
        delaunay_counts_apa1=delaunay_counts[1],
        graph_apa0=graph_apa0,
        graph_apa1=graph_apa1,
        sample_name_apa0=name0,
        sample_name_apa1=name1,
    )


def _compute_edge_accounting(
    arrays: dict,
    sp_apa_all: np.ndarray,
    graph_apa0: NuGraphData,
    graph_apa1: NuGraphData,
) -> list[EdgeAccountingEntry]:
    entries = []

    def _count_ei(ei_tensor):
        if ei_tensor is None:
            return 0
        t = ei_tensor
        return int(t.shape[1]) if (t.dim() == 2 and t.shape[1] > 0) else 0

    def _count_arr(ei):
        return int(ei.shape[1]) if ei.shape[1] > 0 else 0

    # SP-SP nexus edges
    sp_sp_src = _load_edge_index(arrays, "sp_nexus_sp/edge_index")
    n_src_spsp = _count_arr(sp_sp_src)
    if n_src_spsp > 0:
        src, dst = sp_sp_src[0], sp_sp_src[1]
        cross = int(np.sum(sp_apa_all[src] != sp_apa_all[dst]))
    else:
        cross = 0
    entries.append(EdgeAccountingEntry(
        field="sp_nexus_sp/edge_index",
        source_count=n_src_spsp,
        apa0_retained=_count_ei(graph_apa0["sp", "nexus", "sp"].get("edge_index")),
        apa1_retained=_count_ei(graph_apa1["sp", "nexus", "sp"].get("edge_index")),
        cross_apa_discarded=cross,
    ))

    # SP supervision edges
    sp_el_src = _load_edge_index(arrays, "sp/edge_label_index")
    n_src_el = _count_arr(sp_el_src)
    if n_src_el > 0:
        src, dst = sp_el_src[0], sp_el_src[1]
        cross_el = int(np.sum(sp_apa_all[src] != sp_apa_all[dst]))
    else:
        cross_el = 0
    # Supervision is stored on sp store, edge_label_index; dummy injected when empty
    el0 = graph_apa0["sp"].get("edge_label_index")
    el1 = graph_apa1["sp"].get("edge_label_index")
    # Dummy edges (single (0,0)) are not real edges
    def _count_supervision(t):
        if t is None:
            return 0
        if t.dim() == 2 and t.shape[1] == 1 and t[0, 0] == 0 and t[1, 0] == 0:
            return 0  # dummy
        return int(t.shape[1]) if t.dim() == 2 else 0
    entries.append(EdgeAccountingEntry(
        field="sp/edge_label_index",
        source_count=n_src_el,
        apa0_retained=_count_supervision(el0),
        apa1_retained=_count_supervision(el1),
        cross_apa_discarded=cross_el,
    ))

    # Plane nexus edges
    for pname in PLANE_NAMES:
        nex_src = _load_edge_index(arrays, f"{pname}_nexus_sp/edge_index")
        n_src_nex = _count_arr(nex_src)
        # Nexus edges are guaranteed intra-APA by TSL; cross count should be 0
        if n_src_nex > 0:
            p_apa_all = arrays[f"{pname}/apa"].flatten().astype(np.int64)
            p_src, sp_dst = nex_src[0], nex_src[1]
            cross_nex = int(np.sum(p_apa_all[p_src] != sp_apa_all[sp_dst]))
        else:
            cross_nex = 0
        nex0 = graph_apa0[pname, "nexus", "sp"].get("edge_index")
        nex1 = graph_apa1[pname, "nexus", "sp"].get("edge_index")
        entries.append(EdgeAccountingEntry(
            field=f"{pname}_nexus_sp/edge_index",
            source_count=n_src_nex,
            apa0_retained=_count_ei(nex0),
            apa1_retained=_count_ei(nex1),
            cross_apa_discarded=cross_nex,
        ))

    return entries


# ---------------------------------------------------------------------------
# CLI entry-point (one-event prototype)
# ---------------------------------------------------------------------------

def _main():
    import argparse, sys

    parser = argparse.ArgumentParser(description="Adapt TSL H5 → canonical NuGraph H5")
    parser.add_argument("tsl_h5",    help="Input TSL HDF5 path")
    parser.add_argument("output_h5", help="Output canonical HDF5 path")
    parser.add_argument("--campaign", default="haiwang-proto-v1")
    parser.add_argument("--sample",   default=None)
    parser.add_argument("--no-topology-gate", action="store_true")
    args = parser.parse_args()

    try:
        result = adapt_tsl_to_canonical(
            args.tsl_h5,
            args.output_h5,
            campaign_id=args.campaign,
            sample_name=args.sample,
            topology_gate=not args.no_topology_gate,
        )
    except TopologyGateError as exc:
        print(f"TOPOLOGY GATE: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"\n=== Adaptation result ===")
    print(f"Run/Subrun/Event : {result.run}/{result.subrun}/{result.event}")
    print(f"Topology source  : {result.topology_source} ({result.topology_name})")
    print(f"SP nodes         : source={result.nsp_source} APA0={result.nsp_apa0} APA1={result.nsp_apa1}")
    for pname in PLANE_NAMES:
        s = result.plane_counts_source[pname]
        a0 = result.plane_counts_apa0[pname]
        a1 = result.plane_counts_apa1[pname]
        print(f"{pname} nodes         : source={s} APA0={a0} APA1={a1}")
    print(f"\nEdge accounting:")
    for e in result.edge_accounting:
        ok = "OK" if e.check_conservation() else "FAIL(conservation)"
        print(
            f"  {e.field}: src={e.source_count} "
            f"apa0={e.apa0_retained} apa1={e.apa1_retained} "
            f"cross={e.cross_apa_discarded} [{ok}]"
        )
    print(f"\nDelaunay edges (adapter-derived):")
    for pname in PLANE_NAMES:
        a0 = result.delaunay_counts_apa0[pname]
        a1 = result.delaunay_counts_apa1[pname]
        print(f"  {pname}: APA0={a0} APA1={a1}")
    print(f"\nSample names:")
    print(f"  APA0: {result.sample_name_apa0}")
    print(f"  APA1: {result.sample_name_apa1}")


if __name__ == "__main__":
    _main()


__all__ = [
    "PLANE_NAMES",
    "TOPO_CTPC",
    "TOPO_KNN_FALLBACK",
    "AdaptationResult",
    "EdgeAccountingEntry",
    "TopologyGateError",
    "read_tsl_event",
    "build_apa_graph",
    "adapt_tsl_to_canonical",
]
