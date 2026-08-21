# Unified Pipeline Data Case A Regression Report
**Date:** 2026-08-20  
**Phase:** 8 (Data Case A one-event regression)  
**Event:** RSE 18255/1/114446 (nskip=46)

---

## Phase 8A — PBS Accounting

| Item | Value |
|------|-------|
| PBS job ID | 175973.sophia-pbs-01.lab.alcf.anl.gov |
| Host | sophia-gpu-02 |
| Exit_status | 0 (PASS) |
| Walltime used | ~23 min |
| PBS walltime limit | 00:45:00 |
| Driver verdict | PASS |
| Receiver campaign_id | haiwang-nugraph4-canonical-v1 |
| events_received | 1 |
| events_expected | 1 |
| Receiver status | PASS |

**Incident note:** Two prior attempts failed:
- PBS 175961: `apptainer: command not found` — module loads missing from PBS script. Fixed.
- PBS 175971: lar SIGSEGV in MaskSlice (exit=11); receiver hung indefinitely (no exit) until PBS SIGTERM (exit=143). Fixed by adding receiver watchdog (RECEIVER_TIMEOUT+120s) to driver. Lar crash non-deterministic; resubmit succeeded.

---

## Phase 8B — H5 Structure Validation

**File:** `tests/data_caseA/canonical/data_caseA_18255_1_114446.h5`  
**Size:** 2,350,356 bytes  
**SHA256:** `7f1a174a06864c386db0b9af02f35a1108f0d76faef15258d7b87f8e830e728b`  
**.partial:** absent

| Check | Result | Value |
|-------|--------|-------|
| Top-level groups | PASS | dataset, datasize, gen, planes, samples, semantic_classes |
| gen value | PASS | [3] |
| planes | PASS | ['u', 'v', 'y'] |
| semantic_classes | PASS | ['nu', 'cosmic'] |
| Number of samples | PASS | 2 (APA0, APA1) |
| Sample keys | PASS | 18255_1_rec-lab-apa0-114446, 18255_1_rec-lab-apa1-114446 |
| RSE 18255/1/114446 | PASS | present in both samples |
| sp_topology_source | PASS | 1 (CTPC) |
| Split | PASS | both in train |
| sp/features shape APA0 | PASS | (3387, 2) |
| sp/features shape APA1 | PASS | (4194, 2) |
| plane/u/x shape APA0 | PASS | (1045, 5) |
| plane/v/x shape APA0 | PASS | (1213, 5) |
| plane/y/x shape APA0 | PASS | (876, 5) |
| plane/u/x shape APA1 | PASS | (1032, 5) |
| plane/v/x shape APA1 | PASS | (1213, 5) |
| plane/y/x shape APA1 | PASS | (824, 5) |
| sp/reco_bundle_id no -1 | PASS | APA0: range [1,24]; APA1: range [9,24] |
| Truth-free: sp/y_semantic | PASS | all -1 (both APAs) |
| Truth-free: sp/y_instance | PASS | all -1 (both APAs) |
| Truth-free: sp/raw_vtx_dist | PASS | all -1 (both APAs) |
| edge_y / edge_labelable | PASS | all 0 (no labelable edges — correct real-data encoding) |
| evt/y | PASS | [0] placeholder |

---

## Phase 8C — Regression vs Validated Reference

**Reference:** `engineering-nc-sideband-19evt-corrected/one_event_smoke/canonical/caseA_18255_1_114446.h5`

| Field | APA 0 | APA 1 |
|-------|-------|-------|
| sp/features shape | (3387,2) MATCH | (4194,2) MATCH |
| sp/reco_bundle_id | bitwise identical | bitwise identical |
| plane/u/x | (1045,5) bitwise identical | (1032,5) bitwise identical |
| plane/v/x | (1213,5) bitwise identical | (1213,5) bitwise identical |
| plane/y/x | (876,5) bitwise identical | (824,5) bitwise identical |
| sp_topology_source | 1 MATCH | 1 MATCH |
| sp/features[:5] row 0 | [2070.9521, 1.0] identical | [13257.344, 9.0] identical |
| All fields (38 compound dtype) | BITWISE IDENTICAL | BITWISE IDENTICAL |

**VERDICT: BITWISE MATCH. All 38 fields across both APA samples are bitwise identical to the validated reference.**

---

## Phase 8 Summary

All checks PASS. The unified production driver `--mode data` produces output that is structurally correct and bitwise identical to the previously validated Case A reference H5. The data pipeline uses the correct canonical contract: gen=3, sp/features (N,2), plane/x (M,5), topology_source=CTPC, truth-free labels, no -1 sentinels in reco_bundle_id.
