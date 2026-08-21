# Unified NuGraph Production Driver

Single entry point for canonical NuGraph4 H5 production from both simulation and real SBND data.

**Validated:** 2026-08-20 on Sophia HPC  
**Status:** PASS — one-event and three-event regressions complete

---

## Quick Start

```bash
bash bin/run_nugraph_production.sh \
    --mode sim|data \
    --manifest MANIFEST.csv \
    --output-h5 OUTPUT.h5 \
    --output-dir OUTPUT_DIR \
    --report OUTPUT_DIR/logs/receiver_report.json
```

Add `--dry-run` to run preflight only (no jobs submitted).

---

## Manifests

Format: `source_index,input_file,nskip,run,subrun,event,input_sha256`

- **Sim:** `nskip` is documentation only; lar runs `--nskip 0 -n N_EVENTS` (single session)
- **Data:** `nskip` is used; lar runs `--nskip N -n 1` (one session per event)

Use `--receiver-manifest` to specify a separate receiver manifest (data mode: excludes known WCT-crash events).

---

## PBS Templates

| Script | Mode | Purpose |
|--------|------|---------|
| `pbs/run_nugraph_data_caseA.pbs` | data | 1-event Case A regression |
| `pbs/run_nugraph_sim_one_event.pbs` | sim | 1-event sim regression |
| `pbs/run_nugraph_data_3event.pbs` | data | 3-event Phase 10 test |
| `pbs/run_nugraph_sim_3event.pbs` | sim | 3-event Phase 10 test |
| `pbs/run_nugraph_data.pbs` | data | Full 19-event corrected data run |
| `pbs/run_nugraph_sim.pbs` | sim | Full 50-event sim run |

Queue: `by-gpu / neutrinoGPU::wirecell_2026`

---

## Frozen Provenance

| Component | SHA |
|-----------|-----|
| WCT | bc7f4af9 |
| larwirecell | 9295e2a3 |
| Receiver | cf0f9d65 |
| Sim FCL | 857af5c3 |
| Data FCL | 0650836f |
| Campaign ID | haiwang-nugraph4-canonical-v1 |

---

## Constraints

- Do NOT commit, push, or modify frozen reference H5 files
- Do NOT modify WCT/larwirecell source
- Do NOT use `nc_sideband_reco2_paths_for_conversion.txt` — use `nc_sideband_exact_reco2_paths.txt`
- Data mode: use `nc_sideband_exact_19events_corrected_manifest.csv` as producer manifest

---

## Reports

All validation reports are in `reports/`:

- `UNIFIED_PIPELINE_EXISTING_WORKFLOW_AUDIT_2026-08-20.md` — Phase 1 component audit
- `SIM_SOURCE_STATE_INTEGRITY_AUDIT_2026-08-20.md` — Phase 7.5 source-state audit
- `UNIFIED_DATA_CASEA_REGRESSION_2026-08-20.md` — Phase 8 data one-event
- `UNIFIED_SIM_ONE_EVENT_REGRESSION_2026-08-20.md` — Phase 9 sim one-event
- `UNIFIED_DATA_3EVENT_REGRESSION_2026-08-20.md` — Phase 10 data multi-event
- `UNIFIED_SIM_3EVENT_REGRESSION_2026-08-20.md` — Phase 10 sim multi-event
- `SIM_VS_DATA_CANONICAL_CONTRACT.md` — Phase 11 schema contract
- `UNIFIED_NUGRAPH_PRODUCTION_VALIDATION_2026-08-20.md` — Phase 11 master validation summary
