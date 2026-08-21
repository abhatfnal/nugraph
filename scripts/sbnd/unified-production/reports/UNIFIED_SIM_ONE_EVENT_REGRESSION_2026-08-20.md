# Unified Pipeline Sim One-Event Regression Report
**Date:** 2026-08-20  
**Phase:** 9 (Sim one-event regression)  
**Event:** RSE 1/2728/1 (source_index=0, nskip=0)

---

## Phase 9A — PBS Accounting

| Item | Value |
|------|-------|
| PBS job ID | 175972.sophia-pbs-01.lab.alcf.anl.gov |
| Host | sophia-gpu-02 |
| Exit_status | 0 (PASS) |
| Driver verdict | PASS |
| Receiver campaign_id | haiwang-nugraph4-canonical-v1 |
| events_received | 1 |
| events_expected | 1 |
| Receiver status | PASS |
| Output H5 size | 2,006,024 bytes |
| SHA256 | 0e95c519a7193cde33d31a5aff6ccaff51c4df5943e694b61b806671cada393a |
| .partial | absent |

**Incident note:** PBS 175962 (first attempt) failed: `apptainer: command not found` and `debug` queue invalid on Sophia. Both fixed: module loads added, queue corrected to `by-gpu / neutrinoGPU::wirecell_2026`.

---

## Phase 9B — RSE (1,2728,1) in Frozen Reference

**Reference:** `engineering-sample-50evt-debug/canonical/haiwang-nugraph4-canonical-v1.h5` (SHA prefix d3c1aaef)  
Found in: `1_2728_rec-lab-apa0-1` and `1_2728_rec-lab-apa1-1`

---

## Phase 9C — Reconstruction Array Comparison

| Field | APA 0 | APA 1 |
|-------|-------|-------|
| sp/features | (4915,2) BITWISE IDENTICAL | (1843,2) BITWISE IDENTICAL |
| sp/pos | (4915,3) BITWISE IDENTICAL | (1843,3) BITWISE IDENTICAL |
| sp/reco_bundle_id | BITWISE IDENTICAL | BITWISE IDENTICAL |
| sp/reco_segment_id | BITWISE IDENTICAL | BITWISE IDENTICAL |
| sp/edge_label_index | BITWISE IDENTICAL | BITWISE IDENTICAL |
| sp/edge_y | (14921,) BITWISE IDENTICAL | (4852,) BITWISE IDENTICAL |
| sp/edge_labelable | BITWISE IDENTICAL | BITWISE IDENTICAL |
| plane/u/x | (510,5) BITWISE IDENTICAL | (470,5) BITWISE IDENTICAL |
| plane/v/x | (903,5) BITWISE IDENTICAL | (437,5) BITWISE IDENTICAL |
| plane/y/x | (786,5) BITWISE IDENTICAL | (340,5) BITWISE IDENTICAL |
| All nexus + plane-plane edges | BITWISE IDENTICAL | BITWISE IDENTICAL |
| metadata/sp_topology_source | 1 MATCH | 1 MATCH |
| All 38 compound fields | BITWISE IDENTICAL | BITWISE IDENTICAL |

**VERDICT: BITWISE MATCH across all 38 fields in both APA samples.**

---

## Phase 9D — Truth Contract

| Check | APA 0 | APA 1 |
|-------|-------|-------|
| sp/features (N,2) | PASS: (4915,2) | PASS: (1843,2) |
| plane/u/x (M,5) | PASS: (510,5) | PASS: (470,5) |
| plane/v/x (M,5) | PASS: (903,5) | PASS: (437,5) |
| plane/y/x (M,5) | PASS: (786,5) | PASS: (340,5) |
| sp/y_semantic not all -1 | PASS: unique=[-1,1] | PASS: unique=[-1,0,1] |
| sp/y_instance present | PASS | PASS |
| sp/raw_vtx_dist (vertex signal) | PASS: range [-1, 4738] | PASS: range [-1, 4695] |
| sp/edge_y meaningful | PASS: unique=[0,1] | PASS: unique=[0,1] |
| sp/edge_labelable meaningful | PASS: unique=[0,1] | PASS: unique=[0,1] |
| sp/reco_bundle_id no -1 | PASS: 0 sentinels | PASS: 0 sentinels |
| sp_topology_source=1 | PASS | PASS |
| Candidate topology reconstruction-derived | PASS: topology_source=CTPC(1) — topology edges come from reconstruction, truth supervises (edge_y/edge_labelable) but does not create them | PASS |
| Split | train | train |

**Vertex encoding:** `sp/raw_vtx_dist` encodes vertex signal (distance of each SP from true vertex; -1.0 sentinel for undefined). No explicit `vertex_label` field; vertex supervision is through raw_vtx_dist.

---

## Phase 9E — NuGraph4 Transform Compatibility

| Check | Value | Verdict |
|-------|-------|---------|
| /gen value | [3] int64 | PASS |
| /dataset group | present | PASS |
| /samples group | present | PASS |
| /planes | ['u','v','y'] | PASS |
| /semantic_classes | ['nu','cosmic'] | PASS |
| sp/ fields (10) | present in both samples | PASS |
| plane fields (15) | present in both samples | PASS |
| Schema vs 50-event reference | bitwise identical dtype layout | PASS |

---

## Phase 9F — No-Intermediate Audit

No intermediate files created outside expected runtime subdirectories:
- `nointermediate-debug-bee.zip` is expected design output from `wcls-img-clus-matching-xin-noint.jsonnet` (created in per-event runtime dir, not output dir); not banned by absent-file check
- No `*.npz`, `nugraph.h5`, `mabc.zip`, `truth*.json`, `trash-all-apa.tar.gz` found in output dir

---

## Phase 9 Summary

All checks PASS. The unified production driver `--mode sim` produces output that is bitwise identical to the corresponding RSE (1,2728,1) entries in the frozen 50-event reference H5 (SHA d3c1aaef). The sim truth contract is satisfied: semantic labels, instance labels, vertex distance, edge_y/edge_labelable all present and meaningful. Candidate topology is reconstruction-derived (CTPC). NuGraph4 Transform compatibility confirmed (gen=3, compound-dtype layout).

**WCT/larwirecell provenance:** bc7f4af9 / 9295e2a3 (corrected from historical git HEAD underdescription; see SIM_SOURCE_STATE_INTEGRITY_AUDIT_2026-08-20.md)
