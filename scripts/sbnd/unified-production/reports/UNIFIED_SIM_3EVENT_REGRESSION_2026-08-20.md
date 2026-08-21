# Unified Pipeline Sim 3-Event Multi-Event Regression Report
**Date:** 2026-08-20  
**Phase:** 10 (sim multi-event)  
**Events:** 1/2728/1, 1/2728/2, 1/2728/3 (single lar session, same ROOT file)

---

## PBS Accounting

| Item | Value |
|------|-------|
| PBS job ID | 175975.sophia-pbs-01.lab.alcf.anl.gov |
| Exit_status | 0 (PASS) |
| Walltime used | 00:04:51 |
| events_received | 3 |
| events_expected | 3 |
| Receiver status | PASS |
| Output H5 size | 3,964,796 bytes |
| SHA256 prefix | 07b33378 |
| .partial | absent |

---

## H5 Structure

| Check | Result |
|-------|--------|
| Number of samples | PASS: 6 (2 APAs × 3 events) |
| All 3 RSEs present | PASS: 1/2728/1, 1/2728/2, 1/2728/3 |
| gen=3 | PASS |
| sp/features (N,2) all samples | PASS |
| sp/reco_bundle_id no -1 | PASS (all 6 samples) |
| sp/y_semantic NOT all -1 | PASS (truth-bearing sim) |

## Per-Sample Shapes

| Sample | sp/features |
|--------|-------------|
| APA0, event 1/2728/1 | (4915, 2) |
| APA1, event 1/2728/1 | (1843, 2) |
| APA0, event 1/2728/2 | (2817, 2) |
| APA1, event 1/2728/2 | (1188, 2) |
| APA0, event 1/2728/3 | (2026, 2) |
| APA1, event 1/2728/3 | (675, 2) |

## Split Assignments

| RSE | Split |
|-----|-------|
| 1/2728/1 | train |
| 1/2728/2 | validation |
| 1/2728/3 | train |

Consistent with frozen 50-event reference (deterministic blake2b hash).

## Regression vs Frozen 50-Event Reference

All 38 compound-dtype fields compared for all 4 new samples (1/2728/2 and 1/2728/3, 2 APAs each):

| RSE | APA | All 38 fields |
|-----|-----|---------------|
| 1/2728/2 | 0 | BITWISE IDENTICAL |
| 1/2728/2 | 1 | BITWISE IDENTICAL |
| 1/2728/3 | 0 | BITWISE IDENTICAL |
| 1/2728/3 | 1 | BITWISE IDENTICAL |

RSE 1/2728/1 spot-checked: sp/features[0] matches reference (already confirmed bitwise identical in Phase 9).

## TrackFitting State Reset Validation

Events 1/2728/2 and 1/2728/3 were produced in the **same single lar session** as event 1/2728/1, running `lar --nskip 0 -n 3`. The frozen reference was produced with 50 events in a single session (original validated run). Both new events are bitwise identical to the reference, confirming that `TrackFitting.clear_segments()` correctly resets state between events and that `TaggerCheckSTM.clear_segments()` clears the global reconstruction state before each event's component loop. **No state contamination detected.**

## Verdict: PASS

All 3 events correctly encoded, bitwise identical to frozen reference for new events. TrackFitting lifetime fix (bc7f4af9) validated across multi-event single-session execution.
