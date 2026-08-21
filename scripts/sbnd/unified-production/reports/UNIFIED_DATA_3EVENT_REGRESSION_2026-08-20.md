# Unified Pipeline Data 3-Event Multi-Event Regression Report
**Date:** 2026-08-20  
**Phase:** 10 (data multi-event)  
**Events:** 18255/1/114446, 18255/1/142421, 18255/1/180801 (3 distinct ROOT files)

---

## PBS Accounting

| Item | Value |
|------|-------|
| PBS job ID | 175974.sophia-pbs-01.lab.alcf.anl.gov |
| Exit_status | 0 (PASS) |
| Walltime used | 00:03:38 |
| events_received | 3 |
| events_expected | 3 |
| Receiver status | PASS |
| Output H5 size | 7,145,668 bytes |
| SHA256 prefix | 8d53703b |
| .partial | absent |

---

## H5 Structure

| Check | Result |
|-------|--------|
| Number of samples | PASS: 6 (2 APAs × 3 events) |
| All 3 RSEs present | PASS: 18255/1/114446, 18255/1/142421, 18255/1/180801 |
| gen=3 | PASS |
| sp_topology_source=1 (all samples) | PASS |
| sp/features shape (N,2) (all samples) | PASS |
| plane/x shape (M,5) (all samples) | PASS |
| reco_bundle_id no -1 (all samples) | PASS |
| Truth-free: y_semantic all -1 | PASS (all 6 samples) |
| Truth-free: y_instance all -1 | PASS (all 6 samples) |
| Truth-free: raw_vtx_dist all -1 | PASS (all 6 samples) |

## Per-Sample Details

| Sample | sp/features shape | topology_source | reco_bundle_id |
|--------|-------------------|-----------------|----------------|
| apa0-114446 | (3387, 2) | 1 | no -1 |
| apa0-142421 | (2924, 2) | 1 | no -1 |
| apa0-180801 | (4892, 2) | 1 | no -1 |
| apa1-114446 | (4194, 2) | 1 | no -1 |
| apa1-142421 | (3362, 2) | 1 | no -1 |
| apa1-180801 | (4448, 2) | 1 | no -1 |

## Split Assignments

| RSE | Split |
|-----|-------|
| 18255/1/114446 | train |
| 18255/1/142421 | test |
| 18255/1/180801 | train |

Deterministic via blake2b hash of `haiwang-nugraph4-canonical-v1` + RSE string.

## Consistency with Single-Event Reference

RSE 18255/1/114446 in the 3-event H5 is **bitwise identical** (allclose=True, max diff=0) to the Case A single-event reference (`caseA_18255_1_114446.h5`). Multi-session receiver correctly preserves per-event fidelity.

## Verdict: PASS

All 3 events correctly encoded across 3 separate lar sessions (one per event). Multi-session receiver handles 3 connections, finalizes all events, produces correct truth-free real-data H5.
