"""Unit tests for pywcml/adapt_tsl.py.

All tests use synthetic in-memory arrays — no H5 file I/O.
Tests cover the pure-core functions: build_apa_graph, _filter_sp_sp,
_filter_sp_sp_supervised, _build_plane_store, and the topology gate.
"""

import numpy as np
import torch
import unittest
import sys
import os

NUGRAPH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if NUGRAPH not in sys.path:
    sys.path.insert(0, NUGRAPH)

from pywcml.adapt_tsl import (
    PLANE_NAMES,
    TOPO_CTPC,
    TOPO_KNN_FALLBACK,
    TopologyGateError,
    _filter_sp_sp,
    _filter_sp_sp_supervised,
    _load_edge_index,
    _sorted_edge_pairs,
    build_apa_graph,
)


# ---------------------------------------------------------------------------
# Helpers for building synthetic array dicts
# ---------------------------------------------------------------------------

def _make_tsl_arrays(
    nsp_apa0: int = 3,
    nsp_apa1: int = 2,
    nplane_apa0: int = 2,
    nplane_apa1: int = 2,
    topology_source: int = TOPO_CTPC,
    cross_sp_sp: bool = False,
    cross_nexus: bool = False,
):
    """Construct a minimal synthetic TSL array dict for testing.

    SP indices 0..nsp_apa0-1 belong to APA0; nsp_apa0..total-1 to APA1.
    Plane indices 0..nplane_apa0-1 belong to APA0; rest to APA1.
    """
    Nsp_total = nsp_apa0 + nsp_apa1
    nplane_total = nplane_apa0 + nplane_apa1

    sp_apa = np.array([0] * nsp_apa0 + [1] * nsp_apa1, dtype=np.int64)
    sp_face = np.zeros(Nsp_total, dtype=np.int64)

    # sp/pos: (N, 3)
    sp_pos = np.random.rand(Nsp_total, 3).astype(np.float32)

    # sp/reco_segment_id and sp/reco_bundle_id
    sp_reco_seg = np.arange(Nsp_total, dtype=np.int64)
    sp_reco_bund = np.arange(Nsp_total, dtype=np.int64) * 2

    # sp/features: (N, 6) — col0=charge, col1=reco_seg (backward-compat invariant)
    sp_feat6 = np.zeros((Nsp_total, 6), dtype=np.float32)
    sp_feat6[:, 0] = np.arange(Nsp_total, dtype=np.float32) * 0.5  # charge
    sp_feat6[:, 1] = sp_reco_seg.astype(np.float32)                # reco_seg

    sp_y_sem = np.zeros(Nsp_total, dtype=np.int64)
    sp_y_inst = np.arange(Nsp_total, dtype=np.int64)
    sp_raw_vtx = np.arange(Nsp_total, dtype=np.float32) * 0.1

    # SP-SP nexus edges: intra-APA pairs only (or with cross-APA if requested)
    if Nsp_total >= 2:
        # APA0: 0-1 if nsp_apa0>=2
        sp_sp_src = []
        sp_sp_dst = []
        if nsp_apa0 >= 2:
            sp_sp_src.append(0); sp_sp_dst.append(1)
        if nsp_apa1 >= 2:
            a, b = nsp_apa0, nsp_apa0 + 1
            sp_sp_src.append(a); sp_sp_dst.append(b)
        if cross_sp_sp and nsp_apa0 >= 1 and nsp_apa1 >= 1:
            # Add one cross-APA edge (should be discarded)
            sp_sp_src.append(0); sp_sp_dst.append(nsp_apa0)
        if sp_sp_src:
            sp_sp_ei = np.array([sp_sp_src, sp_sp_dst], dtype=np.int64)
        else:
            # dummy
            sp_sp_ei = np.array([[0], [0]], dtype=np.int64)
    else:
        sp_sp_ei = np.array([[0], [0]], dtype=np.int64)

    # SP supervision = same topology
    sp_el_ei = sp_sp_ei.copy()
    E_label = sp_sp_ei.shape[1]
    sp_ey = np.ones(E_label, dtype=np.int64)
    sp_el = np.ones(E_label, dtype=np.int64)

    # Plane arrays
    p_apa = np.array([0] * nplane_apa0 + [1] * nplane_apa1, dtype=np.int64)
    p_face = np.zeros(nplane_total, dtype=np.int64)
    p_pos = np.random.rand(nplane_total, 2).astype(np.float32)
    p_x15 = np.random.rand(nplane_total, 15).astype(np.float32)
    p_y_sem = np.zeros(nplane_total, dtype=np.int64)
    p_y_inst = np.arange(nplane_total, dtype=np.int64)

    # Nexus edges (plane -> SP): intra-APA only
    nexus_src_apa0 = list(range(nplane_apa0))
    nexus_dst_apa0 = [i % nsp_apa0 for i in range(nplane_apa0)]
    nexus_src_apa1 = [nplane_apa0 + i for i in range(nplane_apa1)]
    nexus_dst_apa1 = [nsp_apa0 + (i % nsp_apa1) for i in range(nplane_apa1)]
    nex_src = nexus_src_apa0 + nexus_src_apa1
    nex_dst = nexus_dst_apa0 + nexus_dst_apa1
    if nex_src:
        nex_ei = np.array([nex_src, nex_dst], dtype=np.int64)
    else:
        nex_ei = np.array([[0], [0]], dtype=np.int64)

    evt_y = np.array([1], dtype=np.int64)

    arrays = {
        "metadata/run":    np.array([1], dtype=np.int64),
        "metadata/subrun": np.array([0], dtype=np.int64),
        "metadata/event":  np.array([1], dtype=np.int64),
        "metadata/sp_topology_source": np.array([topology_source], dtype=np.int64),
        "sp/apa":           sp_apa,
        "sp/face":          sp_face,
        "sp/pos":           sp_pos,
        "sp/features":      sp_feat6,
        "sp/reco_segment_id": sp_reco_seg,
        "sp/reco_bundle_id":  sp_reco_bund,
        "sp/y_semantic":    sp_y_sem,
        "sp/y_instance":    sp_y_inst,
        "sp/raw_vtx_dist":  sp_raw_vtx,
        "sp_nexus_sp/edge_index": sp_sp_ei,
        "sp/edge_label_index": sp_el_ei,
        "sp/edge_y":        sp_ey,
        "sp/edge_labelable": sp_el,
        "evt/y":            evt_y,
    }

    for pname in PLANE_NAMES:
        arrays[f"{pname}/apa"]       = p_apa
        arrays[f"{pname}/face"]      = p_face
        arrays[f"{pname}/pos"]       = p_pos
        arrays[f"{pname}/x"]         = p_x15
        arrays[f"{pname}/y_semantic"] = p_y_sem
        arrays[f"{pname}/y_instance"] = p_y_inst
        arrays[f"{pname}_nexus_sp/edge_index"] = nex_ei

    return arrays, sp_apa, p_apa


# ===========================================================================
# Tests
# ===========================================================================


class TestLoadEdgeIndex(unittest.TestCase):
    """_load_edge_index: TSL dummy detection."""

    def test_real_edge_preserved(self):
        arrays = {"ei": np.array([[1, 2], [3, 4]], dtype=np.int64)}
        ei = _load_edge_index(arrays, "ei")
        assert ei.shape == (2, 2)
        np.testing.assert_array_equal(ei[0], [1, 2])
        np.testing.assert_array_equal(ei[1], [3, 4])

    def test_dummy_becomes_empty(self):
        # TSL writes [[0],[0]] when no real edges
        arrays = {"ei": np.array([[0], [0]], dtype=np.int64)}
        ei = _load_edge_index(arrays, "ei")
        assert ei.shape == (2, 0)

    def test_single_real_edge_not_treated_as_dummy(self):
        # (0, 1) is a real edge, not a dummy
        arrays = {"ei": np.array([[0], [1]], dtype=np.int64)}
        ei = _load_edge_index(arrays, "ei")
        assert ei.shape == (2, 1)
        assert ei[1, 0] == 1

    def test_single_zero_zero_is_dummy(self):
        arrays = {"ei": np.array([[0], [0]], dtype=np.int64)}
        ei = _load_edge_index(arrays, "ei")
        assert ei.shape == (2, 0)


class TestSortedEdgePairs(unittest.TestCase):
    """_sorted_edge_pairs: lexicographic sort."""

    def test_sorted_order(self):
        ei = np.array([[2, 0, 1], [3, 2, 4]], dtype=np.int64)
        out = _sorted_edge_pairs(ei)
        pairs = list(zip(out[0].tolist(), out[1].tolist()))
        assert pairs == sorted(pairs)

    def test_empty_passthrough(self):
        ei = np.empty((2, 0), dtype=np.int64)
        out = _sorted_edge_pairs(ei)
        assert out.shape == (2, 0)

    def test_deterministic(self):
        ei = np.array([[5, 1, 3], [6, 2, 4]], dtype=np.int64)
        a = _sorted_edge_pairs(ei)
        b = _sorted_edge_pairs(ei)
        np.testing.assert_array_equal(a, b)


class TestFilterSpSp(unittest.TestCase):
    """_filter_sp_sp: APA partition of SP-SP edges."""

    def test_intra_apa0_retained(self):
        sp_apa = np.array([0, 0, 1, 1], dtype=np.int64)
        # Edge (0,1): both APA0
        ei = np.array([[0], [1]], dtype=np.int64)
        old_to_new = np.array([0, 1, -1, -1], dtype=np.int64)
        out, cross = _filter_sp_sp(ei, sp_apa, 0, old_to_new)
        assert out.shape == (2, 1)
        assert tuple(out[:, 0].tolist()) == (0, 1)
        assert cross == 0

    def test_intra_apa1_retained(self):
        sp_apa = np.array([0, 0, 1, 1], dtype=np.int64)
        # Edge (2,3): both APA1
        ei = np.array([[2], [3]], dtype=np.int64)
        old_to_new = np.array([-1, -1, 0, 1], dtype=np.int64)
        out, cross = _filter_sp_sp(ei, sp_apa, 1, old_to_new)
        assert out.shape == (2, 1)
        assert tuple(out[:, 0].tolist()) == (0, 1)
        assert cross == 0

    def test_cross_apa_discarded(self):
        sp_apa = np.array([0, 1], dtype=np.int64)
        # Edge (0,1): cross-APA
        ei = np.array([[0], [1]], dtype=np.int64)
        old_to_new = np.array([0, -1], dtype=np.int64)
        out, cross = _filter_sp_sp(ei, sp_apa, 0, old_to_new)
        assert out.shape == (2, 0)
        assert cross == 1

    def test_empty_returns_empty(self):
        sp_apa = np.array([0, 1], dtype=np.int64)
        ei = np.empty((2, 0), dtype=np.int64)
        old_to_new = np.array([0, -1], dtype=np.int64)
        out, cross = _filter_sp_sp(ei, sp_apa, 0, old_to_new)
        assert out.shape == (2, 0)
        assert cross == 0

    def test_index_remapping(self):
        # APA0 has global indices 2, 4 → new indices 0, 1
        sp_apa = np.array([1, 1, 0, 1, 0], dtype=np.int64)
        ei = np.array([[2], [4]], dtype=np.int64)
        old_to_new = np.array([-1, -1, 0, -1, 1], dtype=np.int64)
        out, _ = _filter_sp_sp(ei, sp_apa, 0, old_to_new)
        assert out.shape == (2, 1)
        assert list(out[:, 0]) == [0, 1]


class TestFilterSpSpSupervised(unittest.TestCase):
    """_filter_sp_sp_supervised: label alignment under APA partition."""

    def test_labels_aligned_after_filter(self):
        # SP 0,1 in APA0; SP 2,3 in APA1. Edges: (0,1)[apa0], (2,3)[apa1]
        sp_apa = np.array([0, 0, 1, 1], dtype=np.int64)
        ei = np.array([[0, 2], [1, 3]], dtype=np.int64)
        edge_y = np.array([11, 22], dtype=np.int64)
        edge_lab = np.array([1, 0], dtype=np.int64)
        old_to_new = np.array([0, 1, -1, -1], dtype=np.int64)
        out_ei, out_y, out_lab = _filter_sp_sp_supervised(
            ei, edge_y, edge_lab, sp_apa, 0, old_to_new
        )
        assert out_ei.shape == (2, 1)
        np.testing.assert_array_equal(out_y, [11])
        np.testing.assert_array_equal(out_lab, [1])

    def test_no_edges_yields_dummy(self):
        sp_apa = np.array([0, 1], dtype=np.int64)
        ei = np.empty((2, 0), dtype=np.int64)
        edge_y = np.array([], dtype=np.int64)
        edge_lab = np.array([], dtype=np.int64)
        old_to_new = np.array([0, -1], dtype=np.int64)
        out_ei, out_y, out_lab = _filter_sp_sp_supervised(
            ei, edge_y, edge_lab, sp_apa, 0, old_to_new
        )
        # Dummy: single (0,0) edge with label 0
        assert out_ei.shape == (2, 1)
        assert out_ei[0, 0] == 0 and out_ei[1, 0] == 0
        assert out_y[0] == 0
        assert out_lab[0] == 0

    def test_bundle_segment_ids_preserved(self):
        """Preserved IDs must survive the APA slice without renumbering."""
        arrays, sp_apa, _ = _make_tsl_arrays(nsp_apa0=3, nsp_apa1=2)
        g = build_apa_graph(arrays, 0, 1, 0, 1)
        # reco_bundle_id for APA0 SPs (global idx 0,1,2) = 0,2,4
        expected_bund = torch.tensor([0, 2, 4], dtype=torch.long)
        torch.testing.assert_close(g["sp"].reco_bundle_id, expected_bund)
        # reco_segment_id for APA0 SPs = 0,1,2
        expected_seg = torch.tensor([0, 1, 2], dtype=torch.long)
        torch.testing.assert_close(g["sp"].reco_segment_id, expected_seg)


class TestBuildApaGraph(unittest.TestCase):
    """build_apa_graph: integration over SP partition, plane partition, features."""

    def test_sp_node_count_apa0(self):
        arrays, sp_apa, _ = _make_tsl_arrays(nsp_apa0=3, nsp_apa1=2)
        g = build_apa_graph(arrays, 0, 1, 0, 1)
        assert g["sp"].pos.shape == (3, 3)

    def test_sp_node_count_apa1(self):
        arrays, sp_apa, _ = _make_tsl_arrays(nsp_apa0=3, nsp_apa1=2)
        g = build_apa_graph(arrays, 1, 1, 0, 1)
        assert g["sp"].pos.shape == (2, 3)

    def test_sp_features_exactly_2_cols(self):
        arrays, _, _ = _make_tsl_arrays(nsp_apa0=4, nsp_apa1=3)
        for apa in (0, 1):
            g = build_apa_graph(arrays, apa, 1, 0, 1)
            assert g["sp"].features.shape[1] == 2, (
                f"APA{apa}: expected 2 cols, got {g['sp'].features.shape[1]}"
            )

    def test_sp_features_col0_is_charge(self):
        arrays, _, _ = _make_tsl_arrays(nsp_apa0=3, nsp_apa1=2)
        g = build_apa_graph(arrays, 0, 1, 0, 1)
        # charge = sp_feat6[:, 0] for APA0 SPs (global indices 0,1,2)
        expected_charge = torch.tensor([0.0, 0.5, 1.0], dtype=torch.float32)
        torch.testing.assert_close(g["sp"].features[:, 0], expected_charge)

    def test_sp_features_col1_is_reco_seg_as_float(self):
        arrays, _, _ = _make_tsl_arrays(nsp_apa0=3, nsp_apa1=2)
        g = build_apa_graph(arrays, 0, 1, 0, 1)
        # reco_segment_id for APA0 SPs = 0,1,2 as float32
        expected = torch.tensor([0.0, 1.0, 2.0], dtype=torch.float32)
        torch.testing.assert_close(g["sp"].features[:, 1], expected)

    def test_plane_x_exactly_5_cols(self):
        arrays, _, _ = _make_tsl_arrays(nplane_apa0=3, nplane_apa1=2)
        for apa in (0, 1):
            g = build_apa_graph(arrays, apa, 1, 0, 1)
            for pname in PLANE_NAMES:
                x = g[pname].x
                assert x.shape[1] == 5, (
                    f"APA{apa} {pname}: expected 5 cols, got {x.shape[1]}"
                )

    def test_plane_x_cols_match_first5_of_x15(self):
        np.random.seed(42)
        arrays, _, _ = _make_tsl_arrays(nplane_apa0=2, nplane_apa1=2)
        g = build_apa_graph(arrays, 0, 1, 0, 1)
        # APA0 plane nodes are global indices 0, 1 (p_apa = [0,0,1,1])
        expected_x = torch.as_tensor(
            arrays["u/x"].reshape(-1, 15)[:2, :5], dtype=torch.float32
        )
        torch.testing.assert_close(g["u"].x, expected_x)

    def test_raw_vtx_dist_separate(self):
        arrays, _, _ = _make_tsl_arrays(nsp_apa0=3, nsp_apa1=2)
        g = build_apa_graph(arrays, 0, 1, 0, 1)
        assert hasattr(g["sp"], "raw_vtx_dist")
        assert g["sp"].raw_vtx_dist.shape == (3,)

    def test_sp_raw_vtx_dist_values(self):
        arrays, _, _ = _make_tsl_arrays(nsp_apa0=3, nsp_apa1=2)
        g = build_apa_graph(arrays, 0, 1, 0, 1)
        # APA0 SPs: global idx 0,1,2 → raw_vtx = 0.0, 0.1, 0.2
        expected = torch.tensor([0.0, 0.1, 0.2], dtype=torch.float32)
        torch.testing.assert_close(g["sp"].raw_vtx_dist, expected, atol=1e-6, rtol=0)

    def test_nexus_edge_index_remapped(self):
        """All nexus edge endpoints must be in-APA local index space."""
        arrays, sp_apa, p_apa = _make_tsl_arrays(nsp_apa0=3, nsp_apa1=2,
                                                   nplane_apa0=2, nplane_apa1=2)
        g0 = build_apa_graph(arrays, 0, 1, 0, 1)
        g1 = build_apa_graph(arrays, 1, 1, 0, 1)
        for apa, g in ((0, g0), (1, g1)):
            Nsp_apa = int((sp_apa == apa).sum())
            Np_apa = int((p_apa == apa).sum())
            for pname in PLANE_NAMES:
                nex = g[pname, "nexus", "sp"].edge_index
                if nex.shape[1] > 0:
                    assert nex[0].min() >= 0 and nex[0].max() < Np_apa, (
                        f"APA{apa} {pname}_nexus_sp plane index out of range"
                    )
                    assert nex[1].min() >= 0 and nex[1].max() < Nsp_apa, (
                        f"APA{apa} {pname}_nexus_sp SP index out of range"
                    )

    def test_sp_sp_nexus_remapped(self):
        """SP-SP nexus endpoints must be in-APA local index space."""
        arrays, sp_apa, _ = _make_tsl_arrays(nsp_apa0=3, nsp_apa1=2)
        for apa in (0, 1):
            g = build_apa_graph(arrays, apa, 1, 0, 1)
            Nsp = int((sp_apa == apa).sum())
            nex = g["sp", "nexus", "sp"].edge_index
            if nex.shape[1] > 0:
                assert nex.min() >= 0 and nex.max() < Nsp

    def test_evt_y_preserved(self):
        arrays, _, _ = _make_tsl_arrays()
        arrays["evt/y"] = np.array([1], dtype=np.int64)
        g = build_apa_graph(arrays, 0, 1, 0, 1)
        assert g["evt"].y.item() == 1

    def test_metadata_run_subrun_event(self):
        arrays, _, _ = _make_tsl_arrays()
        g = build_apa_graph(arrays, 0, 42, 7, 99)
        assert g["metadata"].run == 42
        assert g["metadata"].subrun == 7
        assert g["metadata"].event == 99

    def test_sp_total_conservation(self):
        """APA0 + APA1 SP count must equal source total."""
        arrays, sp_apa, _ = _make_tsl_arrays(nsp_apa0=5, nsp_apa1=4)
        g0 = build_apa_graph(arrays, 0, 1, 0, 1)
        g1 = build_apa_graph(arrays, 1, 1, 0, 1)
        assert g0["sp"].pos.shape[0] + g1["sp"].pos.shape[0] == len(sp_apa)

    def test_plane_node_conservation_per_plane(self):
        """APA0 + APA1 plane node count must equal source total for each plane."""
        arrays, _, p_apa = _make_tsl_arrays(nplane_apa0=3, nplane_apa1=4)
        g0 = build_apa_graph(arrays, 0, 1, 0, 1)
        g1 = build_apa_graph(arrays, 1, 1, 0, 1)
        for pname in PLANE_NAMES:
            n_src = len(p_apa)
            n0 = g0[pname].x.shape[0]
            n1 = g1[pname].x.shape[0]
            assert n0 + n1 == n_src, (
                f"{pname}: {n0} + {n1} = {n0+n1} != src {n_src}"
            )


class TestTopologyGate(unittest.TestCase):
    """Topology gate: KNN_FALLBACK events are rejected."""

    def test_knn_fallback_raises_with_gate(self):
        arrays, _, _ = _make_tsl_arrays(topology_source=TOPO_KNN_FALLBACK)
        with self.assertRaises(TopologyGateError):
            build_apa_graph(arrays, 0, 1, 0, 1, topology_gate=True)

    def test_knn_fallback_passes_without_gate(self):
        arrays, _, _ = _make_tsl_arrays(topology_source=TOPO_KNN_FALLBACK)
        g = build_apa_graph(arrays, 0, 1, 0, 1, topology_gate=False)
        assert g is not None

    def test_ctpc_passes_gate(self):
        arrays, _, _ = _make_tsl_arrays(topology_source=TOPO_CTPC)
        g = build_apa_graph(arrays, 0, 1, 0, 1, topology_gate=True)
        assert g is not None

    def test_topology_source_stored_in_metadata(self):
        arrays, _, _ = _make_tsl_arrays(topology_source=TOPO_CTPC)
        g = build_apa_graph(arrays, 0, 1, 0, 1)
        assert hasattr(g["metadata"], "sp_topology_source")
        assert int(g["metadata"].sp_topology_source) == TOPO_CTPC


class TestDelaunayEdges(unittest.TestCase):
    """Delaunay in-plane edges: deterministic and lexicographically sorted."""

    def test_edges_lexicographically_sorted(self):
        np.random.seed(7)
        arrays, _, _ = _make_tsl_arrays(nplane_apa0=6, nplane_apa1=4)
        g = build_apa_graph(arrays, 0, 1, 0, 1)
        for pname in PLANE_NAMES:
            ei = g[pname, "plane", pname].edge_index  # (2, E)
            if ei.shape[1] < 2:
                continue
            pairs = list(zip(ei[0].tolist(), ei[1].tolist()))
            assert pairs == sorted(pairs), (
                f"{pname}: Delaunay edges not lexicographically sorted: {pairs[:5]}"
            )

    def test_edges_deterministic(self):
        np.random.seed(7)
        arrays, _, _ = _make_tsl_arrays(nplane_apa0=6, nplane_apa1=4)
        g1 = build_apa_graph(arrays, 0, 1, 0, 1)
        g2 = build_apa_graph(arrays, 0, 1, 0, 1)
        for pname in PLANE_NAMES:
            ei1 = g1[pname, "plane", pname].edge_index
            ei2 = g2[pname, "plane", pname].edge_index
            torch.testing.assert_close(ei1, ei2)

    def test_single_plane_node_no_edges(self):
        """1 node → no Delaunay edges."""
        arrays, _, _ = _make_tsl_arrays(nplane_apa0=1, nplane_apa1=1)
        g = build_apa_graph(arrays, 0, 1, 0, 1)
        for pname in PLANE_NAMES:
            ei = g[pname, "plane", pname].edge_index
            assert ei.shape[1] == 0, f"{pname}: expected 0 edges, got {ei.shape[1]}"


class TestBothApaSameSplit(unittest.TestCase):
    """Both APA samples from the same physical event must go to the same split."""

    def test_same_split_for_apa0_apa1(self):
        from pywcml.identity import EventIdentity
        id0 = EventIdentity(
            campaign_id="haiwang-proto-v1", shard_id=0, source_index=0,
            run=1, subrun=0, event=1, random_seed=0,
        )
        id1 = EventIdentity(
            campaign_id="haiwang-proto-v1", shard_id=0, source_index=0,
            run=1, subrun=0, event=1, random_seed=0,
        )
        # Same EventIdentity → same split (BLAKE2b is deterministic on same physical_key)
        assert id0.split() == id1.split()
        assert id0.sample_name(0) != id0.sample_name(1)

    def test_apa_suffix_in_sample_name(self):
        from pywcml.identity import EventIdentity
        identity = EventIdentity(
            campaign_id="haiwang-proto-v1", shard_id=0, source_index=0,
            run=42, subrun=7, event=3, random_seed=0,
        )
        n0 = identity.sample_name(0)
        n1 = identity.sample_name(1)
        assert "apa0" in n0
        assert "apa1" in n1
        assert n0 != n1

    def test_prototype_split_is_train(self):
        from pywcml.identity import EventIdentity
        identity = EventIdentity(
            campaign_id="haiwang-proto-v1", shard_id=0, source_index=0,
            run=1, subrun=0, event=1, random_seed=0,
        )
        assert identity.split() == "train"


class TestEdgeConservation(unittest.TestCase):
    """SP-SP cross-APA edges are discarded and accounted for correctly."""

    def test_cross_apa_sp_sp_discarded(self):
        """A cross-APA SP-SP edge must not appear in either APA's graph."""
        nsp_apa0, nsp_apa1 = 3, 2
        arrays, sp_apa, _ = _make_tsl_arrays(
            nsp_apa0=nsp_apa0, nsp_apa1=nsp_apa1, cross_sp_sp=True
        )
        g0 = build_apa_graph(arrays, 0, 1, 0, 1)
        g1 = build_apa_graph(arrays, 1, 1, 0, 1)

        ei0 = g0["sp", "nexus", "sp"].edge_index
        ei1 = g1["sp", "nexus", "sp"].edge_index

        # No endpoint in APA0's edge_index should exceed nsp_apa0-1
        if ei0.shape[1] > 0:
            assert ei0.max() < nsp_apa0
        # No endpoint in APA1's edge_index should exceed nsp_apa1-1
        if ei1.shape[1] > 0:
            assert ei1.max() < nsp_apa1


if __name__ == "__main__":
    unittest.main()
