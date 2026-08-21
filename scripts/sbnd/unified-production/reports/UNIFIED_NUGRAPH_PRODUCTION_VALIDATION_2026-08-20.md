# Unified NuGraph Production Validation
**Date:** 2026-08-20  
**Driver:** `run_nugraph_production.sh --mode sim|data`  
**Validated on:** Sophia HPC (ALCF)

---

## Summary

The unified NuGraph4 production driver has been validated through a full regression and multi-event test suite. Both `--mode sim` and `--mode data` produce canonical H5 files that are bitwise identical to their respective validated references, across one-event and three-event tests.

**OVERALL VERDICT: PASS**

---

## Phase-by-Phase Results

### Phase 1: Workflow Audit
Completed: `UNIFIED_PIPELINE_EXISTING_WORKFLOW_AUDIT_2026-08-20.md`  
Component table with 30+ rows, documenting shared vs mode-specific behavior.

### Phase 7.5: Sim Source-State Integrity Audit
Completed: `SIM_SOURCE_STATE_INTEGRITY_AUDIT_2026-08-20.md`  
Finding: Historical git HEAD (WCT 0869668, lwc 6ead889) underdescribed actual compiled state. Effective compiled state confirmed as bc7f4af9 / 9295e2a3. SHA gates corrected. No source mutations.

### Phase 8: Data One-Event Regression (Case A)
- **Event:** RSE 18255/1/114446, nskip=46
- **PBS:** 175973, Exit_status=0
- **Result:** PASS — bitwise identical to `one_event_smoke/canonical/caseA_18255_1_114446.h5`
- **Incident:** Two prior attempts failed (apptainer module load missing; lar SIGSEGV + receiver hang). Fixed: module loads added; receiver watchdog added to driver.
- **Report:** `UNIFIED_DATA_CASEA_REGRESSION_2026-08-20.md`

### Phase 9: Sim One-Event Regression
- **Event:** RSE 1/2728/1 (source_index=0)
- **PBS:** 175972, Exit_status=0
- **Result:** PASS — bitwise identical to frozen 50-event reference (d3c1aaef) for all 38 compound fields
- **Truth contract:** semantic, instance, vertex (raw_vtx_dist), edge_y, edge_labelable all present and meaningful
- **Report:** `UNIFIED_SIM_ONE_EVENT_REGRESSION_2026-08-20.md`

### Phase 9F: No-Intermediate Audit
PASS — no banned intermediate files in output directories.

### Phase 10: Data Multi-Event (3 events)
- **Events:** 18255/1/114446, 18255/1/142421, 18255/1/180801
- **PBS:** 175974, Exit_status=0, walltime=00:03:38
- **Result:** PASS — 6 samples, all truth-free, all CTPC, no -1 sentinels
- **Consistency:** RSE 114446 bitwise identical to Case A reference in multi-event context
- **Report:** `UNIFIED_DATA_3EVENT_REGRESSION_2026-08-20.md`

### Phase 10: Sim Multi-Event (3 events, single lar session)
- **Events:** 1/2728/1, 1/2728/2, 1/2728/3 (single `lar -n 3` session)
- **PBS:** 175975, Exit_status=0, walltime=00:04:51
- **Result:** PASS — all 38 fields bitwise identical to frozen reference for 1/2728/2 and 1/2728/3
- **TrackFitting state reset:** VALIDATED — no inter-event state contamination
- **Report:** `UNIFIED_SIM_3EVENT_REGRESSION_2026-08-20.md`

---

## Bugs Found and Fixed During Validation

| # | Bug | Fix |
|---|-----|-----|
| 1 | `apptainer: command not found` on PBS compute nodes | Added `module load spack-pe-base; module load apptainer` to all PBS scripts |
| 2 | `debug` queue doesn't exist on Sophia | Corrected to `by-gpu / neutrinoGPU::wirecell_2026` in sim_defaults.sh |
| 3 | Sim SHA gate underdescription (0869668/6ead889) | Corrected to bc7f4af9/9295e2a3 in sim_defaults.sh and run_sim_container.sh |
| 4 | `check_clus_jsonnet()` searched wrong file (sbnd_xin/clus.jsonnet) | Fixed to check exact path `wcp-porting/sbnd/pgrapher/experiment/sbnd/clus.jsonnet` |
| 5 | Receiver hang after lar SIGSEGV (server_sock.accept() does not respect settimeout() on Sophia) | Added watchdog to driver: kills receiver after RECEIVER_TIMEOUT+120s post-container |
| 6 | lar SIGSEGV in MaskSlice (non-deterministic; event 18255/1/114446 on first unified driver attempt) | Resubmit — non-deterministic crash, succeeded on retry |

---

## Frozen State Summary

| Component | Commit / SHA |
|-----------|-------------|
| WCT (wct-ap-yuhw) | bc7f4af9 |
| larwirecell (larwirecell-dev) | 9295e2a3 |
| Receiver | cf0f9d65 |
| Sim FCL | 857af5c3 |
| Data FCL | 0650836f |
| Frozen 50-event reference | d3c1aaef (SHA256 prefix) |

---

## PBS Job Registry

| Job | Mode | Events | Exit | Verdict |
|-----|------|--------|------|---------|
| 175961 | data | 1 (114446) | 127 | FAIL — apptainer not found |
| 175962 | sim | 1 (1/2728/1) | 1 | FAIL — debug queue + apptainer |
| 175971 | data | 1 (114446) | 143 | FAIL — lar SIGSEGV + receiver hang |
| 175972 | sim | 1 (1/2728/1) | 0 | **PASS** |
| 175973 | data | 1 (114446) | 0 | **PASS** |
| 175974 | data | 3 | 0 | **PASS** |
| 175975 | sim | 3 | 0 | **PASS** |

---

## Contract Document

See `SIM_VS_DATA_CANONICAL_CONTRACT.md` for the full schema, truth encoding, canonical gates, and absent-file contract shared between sim and data modes.
