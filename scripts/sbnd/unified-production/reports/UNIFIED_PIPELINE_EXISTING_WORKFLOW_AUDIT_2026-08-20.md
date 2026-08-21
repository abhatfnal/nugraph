# Unified Pipeline Existing Workflow Audit
**Date:** 2026-08-20  
**Purpose:** Phase 1 audit before writing unified production driver.  
**Audited by:** reading all PBS scripts, container scripts, receiver, manifests, and logs.

---

## Component Table

| Component | Simulation (50-event) | Data (19-event corrected) | Common? | Action needed |
|-----------|----------------------|---------------------------|---------|---------------|
| Top-level PBS script | `pbs_ipc_noint_50evt_persistent.pbs` | `pbs_19event_corrected_run.pbs` | No (different paths/params) | Unify outer structure into `run_nugraph_production.sh` |
| Container script | `run_ipc_noint_50evt_persistent.sh` | `run_19event_corrected_container.sh` | No (different steps) | Keep separate; reference by mode |
| Receiver script | `run_canonical_receiver.py` | `run_canonical_receiver.py` | **YES — SAME SCRIPT** | None — single shared receiver |
| Manifest format | `source_index,input_file,nskip,run,subrun,event,input_sha256` | Same columns | **YES — SAME FORMAT** | None |
| Campaign ID (H5 split hash) | `haiwang-nugraph4-canonical-v1` (hardcoded in receiver) | `haiwang-nugraph4-canonical-v1` (same receiver) | **YES — SAME** | None; document that split hash is identical for both modes |
| WCT commit | `bc7f4af9...` (effective; historical git HEAD was `0869668` but built from working-tree patch now at `bc7f4af9`) | `bc7f4af9...` | **YES — SAME** | Common SHA gate (corrected 2026-08-20; see SIM_SOURCE_STATE_INTEGRITY_AUDIT) |
| larwirecell commit | `9295e2a3...` (effective; historical git HEAD was `6ead889` but EventGraphIPC.cxx was uncommitted working-tree file now committed at `9295e2a3`) | `9295e2a3...` | **YES — SAME** | Common SHA gate (corrected 2026-08-20) |
| FCL | `wcls-img-clus-matching-xin-noint.fcl` SHA `857af5c3...` | `wcls-img-clus-matching-xin-data-noint.fcl` SHA `0650836f...` | **NO — DIFFERENT** | Mode-specific FCL gate |
| pywcml directory | `/lus/eagle/.../clustering/nugraph` | `/lus/eagle/.../clustering/nugraph-sophia-dev` | **NO — DIFFERENT** | Mode-specific PYTHONPATH |
| Container type | SLF7 squashfs `slf7.sif` | Same | **YES** | None |
| Overlay images | `larsoft-v10_14_02.squashfs` + `sbnd-v10_14_02_04_delta.squashfs` | Same | **YES** | None |
| Env file | `sbndcode-v10_14_02_04.env` | Same | **YES** | None |
| Apptainer flags | `--fakeroot --bind /lus/eagle --bind /lus/grand --overlay ...` | Same | **YES** | None |
| WCT waf rebuild step | YES (three-part TrackFitting lifetime fix) | NO | No | Sim-only container step |
| wcdoctest-clus step | YES (clear_segments regression gate) | NO | No | Sim-only gate |
| larwirecell cmake rebuild | YES | YES | **YES** | Common container step |
| BNBSpillInfo patch | NO | YES (ClassVersion 15→16) | No | Data-only container step |
| lar session count | 1 (all events in single `lar -n 50`) | N per-event (`lar -n 1` loop) | No | Mode-specific lar invocation |
| Receiver `--max-sessions` | 1 (effectively) | 17 (one per event) | No | Mode-specific receiver arg |
| Producer manifest | 50 rows, 2 unique ROOT files | 19 rows, 19 unique ROOT files | Same format | None |
| Receiver manifest | 50 rows (all same) | 17 rows (WCT-crash events excluded) | Same format | Separate `--receiver-manifest` arg |
| Socket path | `/dev/shm/eventgraph_${JOBID}.sock` | `/dev/shm/nugraph_19evt_corrected_${JOBID}.sock` | Similar pattern | Unify to `/dev/shm/nugraph_${MODE}_${JOBID}.sock` |
| Truth labels | YES (semantic, instance, vertex, edge_y, edge_labelable) | NO (all -1/0, real data) | No | Mode-specific canonical gates in receiver (already handled by receiver build_apa_graph) |
| Canonical gates | topology_source=CTPC, sp.features (N,2), plane.x (M,5), split | Same | **YES** | None — same gates apply |
| Absent-file audit | nugraph.h5, mabc.zip, trash-all-apa.tar.gz, *.npz, truth*.json | Same | **YES** | Identical banned list |
| .partial gate | YES | YES | **YES** | Common gate |
| Output H5 collision check | YES | YES | **YES** | Common preflight |
| Receiver SHA gate | YES (cf0f9d65...) | YES (same) | **YES** | Common gate |
| PBS queue/account | `debug / neutrinoGPU::debug` | `by-gpu / neutrinoGPU::wirecell_2026` | No | Mode-specific PBS headers |
| FHICL_FILE_PATH[0] | `wcp-porting/sbnd` | `validated FCL dir` | Similar | Mode-specific FCL search path |
| WIRECELL_PATH | `wcp-porting/sbnd:wct/cfg:sbnd_xin:photodet:wcd_share` | Same | **YES** | None |
| GCC version | `v12_1_0` | Same | **YES** | None |
| Post-run report | JSON receiver report | Same | **YES** | Common reporting |

---

## Detailed Component Descriptions

### Simulation Workflow

**PBS:** `pbs_ipc_noint_50evt_persistent.pbs`

Steps:
1. Preflight: WCT SHA gate (0869668), larwirecell SHA gate (6ead889), manifest SHA (50 rows), reference H5 SHA, input file SHAs, clus.jsonnet patch check, output H5 collision check, absent-file check
2. Start receiver: `PYTHONPATH=nugraph run_canonical_receiver.py --socket /dev/shm/eventgraph_JOBID.sock --output-h5 ... --expected-manifest source_events_50evt.csv --timeout 480`
3. Run container: `apptainer exec ... bash run_ipc_noint_50evt_persistent.sh`
4. Wait receiver exit

**Container script:** `run_ipc_noint_50evt_persistent.sh`

Steps:
1. SHA gates (redundant with PBS-level)
2. `[1/4]` WCT waf rebuild (TrackFitting lifetime fix: clear_segments in TrackFitting + TaggerCheckSTM)
3. `[2/4]` wcdoctest-clus `*clear_segments*` regression gate
4. `[3/4]` CMake incremental larwirecell rebuild → install to `opt/`
5. `[4/4]` Single `lar --nskip 0 -n 50 -s [SR2728_FILE] -s [SR2236_FILE] -c wcls-img-clus-matching-xin-noint.fcl --no-output`; all 50 events from two ROOT files in one session

**Manifest:** `source_events_50evt.csv`  
50 rows; 48 rows reference SR=2728 ROOT file, 2 rows reference SR=2236 ROOT file.  
`nskip` values are 0..49 (sequential within lar's multi-source event sequence).

**Receiver manifest:** same as producer manifest (50 events, all expected to succeed).

**FCL:** `wcp-porting/sbnd/wcls-img-clus-matching-xin-noint.fcl` — simulation FCL with truth labeling, includes truth-bearing TensorSetLabeler outputs.

**Output:** `engineering-50evt-persistent/canonical/50evt-persistent-canonical.h5`  
Frozen reference: `engineering-sample-50evt-debug/canonical/haiwang-nugraph4-canonical-v1.h5` (SHA `d3c1aaef...`)

---

### Data Workflow

**PBS:** `pbs_19event_corrected_run.pbs`

Steps:
1. Preflight: WCT SHA gate (bc7f4af9), larwirecell SHA gate (9295e2a3), manifest check (19 rows), FCL SHA gate (0650836f), all 19 input file SHAs, clus.jsonnet patch, receiver SHA (cf0f9d65), output H5 collision check, absent-file check
2. Start receiver: `PYTHONPATH=nugraph-sophia-dev run_canonical_receiver.py --socket /dev/shm/nugraph_19evt_corrected_JOBID.sock --output-h5 ... --expected-manifest receiver_manifest_17evt.csv --timeout 900 --inter-session-timeout 600 --max-sessions 17`
3. Run container: `apptainer exec ... bash run_19event_corrected_container.sh`
4. Wait receiver exit
5. Post-run absent-file audit, .partial gate, receiver report, verdict

**Container script:** `run_19event_corrected_container.sh`

Steps:
1. Env setup + SHA gates
2. `[2]` CMake incremental larwirecell rebuild → install to `opt/`
3. `[3]` WIRECELL_PATH + FHICL_FILE_PATH setup
4. `[4]` Manifest check (19 rows)
5. `[4b]` BNBSpillInfo ClassVersion 15→16 patch (rootcling + compile) — first row's ROOT file used as reference
6. `[5]` Loop: 19 × `lar --nskip N -n 1 -c wcls-img-clus-matching-xin-data-noint.fcl --no-output -s INPUT_FILE` (one per manifest row)

**Producer manifest:** `nc_sideband_exact_19events_corrected_manifest.csv` — 19 rows.  
**Receiver manifest:** `nc_sideband_exact_17events_corrected_receiver_manifest.csv` — 17 rows (excludes 18255/1/506114 and 18259/1/37112 which crash in WCT).

**FCL:** `engineering-nc-sideband-19evt-new-pipeline/scripts/19event_run_v1/wcls-img-clus-matching-xin-data-noint.fcl` — real-data FCL, no truth output.

**Output:** `engineering-nc-sideband-19evt-corrected/full_19event_run/canonical/nc_sideband_exact_19events_corrected_canonical.h5`

---

## Key Structural Commonalities

1. **Receiver is identical** — one script handles both modes
2. **Manifest format is identical** — `source_index,input_file,nskip,run,subrun,event,input_sha256`
3. **Campaign ID in H5 split hash is identical** — both use `haiwang-nugraph4-canonical-v1` (receiver hardcoded value)
4. **Canonical gates are identical** — topology_source=CTPC, sp.features (N,2), plane.x (M,5), split in {train,validation,test}
5. **Container images are identical** — same SIF + same overlay squashfs
6. **Absent-file banned list is identical**
7. **PBS outer structure is isomorphic** — start receiver → start container → wait → audit → verdict

---

## Key Structural Differences

| Aspect | Simulation | Data |
|--------|------------|------|
| WCT commit | bc7f4af9 (corrected; historical HEAD was 0869668 but effective compiled source is bc7f4af9) | bc7f4af9 |
| larwirecell commit | 9295e2a3 (corrected; historical HEAD was 6ead889 but EventGraphIPC.cxx was uncommitted, now at 9295e2a3) | 9295e2a3 |
| FCL file | wcls-img-clus-matching-xin-noint.fcl | wcls-img-clus-matching-xin-data-noint.fcl |
| pywcml PYTHONPATH | clustering/nugraph | clustering/nugraph-sophia-dev |
| Container extra steps | WCT waf + doctest | BNBSpillInfo patch |
| lar sessions | 1 (all events) | N (one per event) |
| nskip in manifest | Documentation only; lar uses `--nskip 0 -n N` | Actual skip; lar uses `--nskip N -n 1` |
| Truth in H5 | YES | NO |
| PBS queue | debug / neutrinoGPU::debug | by-gpu / neutrinoGPU::wirecell_2026 |

---

## What Can Be Literally Shared

1. **`run_canonical_receiver.py`** — do not copy or modify
2. Outer PBS structure (preflight → receiver → container → wait → audit → verdict)
3. Common preflight functions: absent-file check, .partial gate, output collision check, receiver SHA gate, clus.jsonnet check, mode-agnostic manifest parsing
4. Apptainer invocation template (same flags, overlays, SIF)
5. Post-run audit logic
6. Verdict reporting

## What Cannot Be Shared

1. WCT/larwirecell SHA gate values (mode-specific frozen commits)
2. FCL file reference and SHA (mode-specific)
3. Container script body (different build steps, different lar invocation)
4. `--max-sessions` value for receiver (1 vs N)
5. nskip usage in lar invocation (not used for sim, used for data)
6. BNBSpillInfo patch (data only)
7. WCT waf rebuild + doctest (sim only)
