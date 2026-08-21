# Sim vs Data Canonical Contract
**Date:** 2026-08-20  
**Unified driver version:** run_nugraph_production.sh --mode sim|data

This document defines the canonical H5 schema that both simulation and real-data modes produce. It is the contract between the producer (unified driver) and the consumer (NuGraph4 training pipeline).

---

## Shared Contract (both modes)

| Property | Value |
|----------|-------|
| Campaign ID | `haiwang-nugraph4-canonical-v1` (hardcoded in receiver; drives deterministic train/val/test split via blake2b hash) |
| WCT commit | bc7f4af9 (TrackFitting lifetime fix + TaggerCheckSTM fix) |
| larwirecell commit | 9295e2a3 (EventGraphIPC.cxx included) |
| Container | slf7.sif + larsoft-v10_14_02.squashfs + sbnd-v10_14_02_04_delta.squashfs |
| Receiver | run_canonical_receiver.py SHA cf0f9d65 |
| gen value | 3 |
| planes | ['u', 'v', 'y'] |
| semantic_classes | ['nu', 'cosmic'] |
| sp/features shape | (N, 2) — NOT (N, 6) old format |
| plane/x shape | (M, 5) per plane — NOT (M, 15) old format |
| sp_topology_source | 1 (CTPC — reconstruction-derived topology) |
| sp/reco_bundle_id | no -1 sentinel values |
| Split labels | deterministic {train, validation, test} from blake2b(campaign_id + RSE) |
| .partial sentinel | absent on clean finalization |
| pywcml path (data) | clustering/nugraph-sophia-dev |
| pywcml path (sim) | clustering/nugraph |

---

## Mode-Specific Contract

| Property | Simulation | Real Data |
|----------|------------|-----------|
| FCL | wcls-img-clus-matching-xin-noint.fcl SHA 857af5c3 | wcls-img-clus-matching-xin-data-noint.fcl SHA 0650836f |
| lar sessions | 1 session (all events in single `lar -n N`) | N sessions (one `lar -n 1` per event) |
| max-sessions (receiver) | 1 | N (one per manifest row) |
| BNBSpillInfo patch | not applied | ClassVersion 15→16 (rootcling + compile, per-job) |
| WCT waf rebuild | YES (TrackFitting/TaggerCheckSTM patches applied) | NO |
| wcdoctest-clus gate | YES (`*clear_segments*` regression) | NO |
| Truth labels | PRESENT — sp/y_semantic, sp/y_instance, sp/raw_vtx_dist, sp/edge_y, sp/edge_labelable | ABSENT — all -1 (sp/y_semantic, sp/y_instance, sp/raw_vtx_dist) or all 0 (edge_y, edge_labelable) |
| evt/y | meaningful nu/cosmic label | 0 placeholder |
| Candidate topology | reconstruction-derived (CTPC); truth supervises via edge_y/edge_labelable | reconstruction-derived (CTPC); no truth supervision |
| PBS queue | by-gpu / neutrinoGPU::wirecell_2026 | by-gpu / neutrinoGPU::wirecell_2026 |
| receiver --timeout | 480s | 900s |
| receiver --inter-session-timeout | 300s | 600s |

---

## Truth Encoding (simulation only)

- **sp/y_semantic**: per-SP semantic label (0=cosmic, 1=nu, -1=undefined/outside fiducial)
- **sp/y_instance**: per-SP instance label (particle ID)
- **sp/raw_vtx_dist**: distance from true neutrino vertex to each SP (float32; -1.0 sentinel for undefined)
- **sp/edge_y**: ground-truth edge label (0=background, 1=signal) — reconstruction topology edges only
- **sp/edge_labelable**: 1 if the edge has a meaningful ground truth, 0 otherwise
- Vertex supervision encoded in raw_vtx_dist (not a discrete vertex_label field)
- Candidate topology edges are reconstruction-derived (CTPC); truth supervises but does not create edges

## Truth Encoding (real data)

- **sp/y_semantic**: all -1 (no truth)
- **sp/y_instance**: all -1 (no truth)
- **sp/raw_vtx_dist**: all -1 (no truth)
- **sp/edge_y**: all 0 (placeholder — 0% labelable)
- **sp/edge_labelable**: all 0 (no edges labeled)
- **evt/y**: 0 (NC-type placeholder)

---

## Canonical Gates (enforced by receiver before writing)

1. `sp_topology_source == 1` (CTPC)
2. `sp/reco_bundle_id`: no -1 sentinel
3. SP conservation: APA0 SPs + APA1 SPs == total SPs
4. Plane conservation: u, v, y
5. `sp/features` shape: (N, 2)
6. `plane/x` shape: (M, 5)
7. Split in {train, validation, test}

---

## Absent-File Contract

The following intermediate files must NOT appear in the output directory tree at job completion:
- `nugraph.h5`
- `mabc.zip`
- `trash-all-apa.tar.gz`
- `*.npz`
- `truth*.json`

Note: `nointermediate-debug-bee.zip` is created by `wcls-img-clus-matching-xin-noint.jsonnet` in the per-event runtime subdirectory. This is expected design behavior and is not banned.
