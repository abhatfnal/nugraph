# Final Git Source State Audit
**Date:** 2026-08-20  
**Purpose:** Verify every validated code component is represented by an immutable pushed commit  
**Platform:** Sophia HPC (ALCF)

---

## Repository Audit Table

| Repository | Branch | Local HEAD | Remote Containing HEAD | Dirty Files | Dirty Files Matter? | Action Required |
|------------|--------|-----------|----------------------|-------------|---------------------|-----------------|
| WCT (`wct-ap-yuhw`) | `pr/nugraph4-wct-integration` | `bc7f4af928921ade590166d5993bca083a4278c0` | `abhatfnal/pr/nugraph4-wct-integration` | `core.3247935` (core dump) | NO — not source | **NONE** |
| larwirecell (`larwirecell-dev`) | `dev-v10_14_02_02` | `9295e2a34c32b5f92ad6483b83dd4895a00b4c9b` | `abhatfnal/dev-v10_14_02_02` | `core.1842860`, `core.769120` (core dumps) | NO — not source | **NONE** |
| NuGraph (`nugraph-sophia-dev`) | `dev/sophia-post-validation-20260818` | `a7c8728e37795d48f4582b395fac716d0585e3b0` | `abhatfnal/feature/nugraph4-beta-sbnd-streaming` | `STDIN.e175468`, `STDIN.o175468` (PBS output) | NO — not source | **NONE** |
| Unified production | (not in git — Eagle directory) | N/A | N/A | All files | YES — needs versioning | **COMMIT to NuGraph** |
| `run_canonical_receiver.py` | (not in git) | N/A | N/A | Entire file | YES | **COMMIT to NuGraph** |

---

## WCT Detail

- **Worktree:** `/lus/eagle/projects/neutrinoGPU/abhat/sbnd/sample_generation_port/work/haiwang-current/wct-ap-yuhw`
- **Branch:** `pr/nugraph4-wct-integration`
- **HEAD:** `bc7f4af928921ade590166d5993bca083a4278c0`
- **Remotes:** `origin` = HaiwangYu/wire-cell-toolkit, `abhatfnal` = abhatfnal/wire-cell-toolkit, `upstream` = WireCell/wire-cell-toolkit
- **Push target:** `abhatfnal/pr/nugraph4-wct-integration` **— HEAD already pushed, PASS**
- **Untracked files:** `core.3247935` (core dump — not source, not committed)
- **Staged/modified:** none
- **Source-state integrity:** The phase 7.5 audit confirmed that the historical git HEAD (`0869668`) underdescribed actual compiled state. The effective compiled state was `bc7f4af9`, now the actual HEAD. No uncommitted source mutations.
- **Key commits on HEAD:**
  - `bc7f4af9` — Merge ap-yuhw into pr/nugraph4-wct-integration
  - `9b1379e` — test(clus): add regression for TrackFitting event-state reset
  - `983495f` — fix(clus): reset TrackFitting state between events

**Action: NONE — already pushed to abhatfnal at validated SHA**

---

## larwirecell Detail

- **Worktree:** `/lus/eagle/projects/neutrinoGPU/abhat/sbnd/sample_generation_port/work/haiwang-current/larwirecell-dev`
- **Branch:** `dev-v10_14_02_02`
- **HEAD:** `9295e2a34c32b5f92ad6483b83dd4895a00b4c9b`
- **Remotes:** `origin` = HaiwangYu/larwirecell, `abhatfnal` = abhatfnal/larwirecell
- **Push target:** `abhatfnal/dev-v10_14_02_02` **— HEAD already pushed, PASS**
- **Untracked files:** `core.1842860`, `core.769120` (core dumps — not source)
- **Staged/modified:** none
- **Key commit on HEAD:**
  - `9295e2a3` — feat(aiml): stream EventGraph over IPC without HDF5 handoff
  - Contains `EventGraphIPC.cxx` (the IPC streaming bridge that eliminated the H5 handoff intermediate)

**Action: NONE — already pushed to abhatfnal at validated SHA**

---

## NuGraph Detail

- **Worktree:** `/lus/eagle/projects/neutrinoGPU/abhat/sbnd/clustering/nugraph-sophia-dev`
- **Branch:** `dev/sophia-post-validation-20260818`
- **HEAD:** `a7c8728e37795d48f4582b395fac716d0585e3b0`
- **Remotes:** `origin` = HaiwangYu/nugraph, `abhatfnal` = abhatfnal/nugraph
- **Push target:** `abhatfnal/feature/nugraph4-beta-sbnd-streaming` **— HEAD already pushed, PASS**
- **Untracked files:** `STDIN.e175468`, `STDIN.o175468` (PBS stdout/stderr output files — not source)
- **Staged/modified:** none
- **Worktree `nugraph` (non-sophia-dev):** `/lus/eagle/projects/neutrinoGPU/abhat/sbnd/clustering/nugraph` — also at `a7c8728e`, also clean
- **pywcml package:** confirmed present in repo at `pywcml/` with all IPC modules
  - `pywcml/eventgraph_ipc.py`
  - `pywcml/recoarrays_ipc.py`
  - `pywcml/trutharrays_ipc.py`
  - `pywcml/h5writer.py`
  - `pywcml/integrated_transaction.py`
  - `pywcml/adapt_tsl.py`, `pywcml/converter.py`, `pywcml/identity.py`, etc.

**Action: COMMIT run_canonical_receiver.py + unified production package on new branch `feature/sbnd-unified-production-20260820`**

---

## run_canonical_receiver.py Status

- **Current location:** `/lus/eagle/projects/neutrinoGPU/abhat/sbnd/sample_generation_port/work/haiwang-current/run_canonical_receiver.py`
- **SHA256:** `cf0f9d65d96ce4fd3f54851c7f9b31e78dfdb3231f543b362232275141cadeb8`
- **In git:** NO — not previously committed to any repository
- **Action:** ADD to NuGraph repo at `scripts/sbnd/run_canonical_receiver.py`

---

## Unified Production Driver Status

- **Current location:** `/lus/eagle/projects/neutrinoGPU/abhat/sbnd/clustering/unified-nugraph-production/`
- **In git:** NO — unversioned Eagle directory
- **Contains:**
  - `bin/run_nugraph_production.sh` — main driver
  - `lib/common.sh`, `lib/containers/*.sh` — common library and mode-specific container scripts
  - `configs/sim_defaults.sh`, `configs/data_defaults.sh` — mode defaults
  - `pbs/*.pbs` — Sophia PBS templates
  - `tests/*/manifest.csv` — gate test manifests
  - `reports/*.md` — all validation reports
  - `README.md`
- **Action:** COPY to `scripts/sbnd/unified-production/` in NuGraph repo; COMMIT and PUSH

---

## FCL Provenance

| FCL | SHA256 | Location | In git |
|-----|--------|----------|--------|
| `wcls-img-clus-matching-xin-noint.fcl` | `857af5c3a4d0fcdfabcda79fedb96770e38b4cdf9a65fb36bbbe40052fadd39a` | `$WORKSPACE/wcp-porting/sbnd/` | NO |
| `wcls-img-clus-matching-xin-data-noint.fcl` | `0650836f9e04842c4bb9b012eac4bedfffeb70db82cc9d1942af307717c171cb` | `engineering-nc-sideband-19evt-new-pipeline/scripts/19event_run_v1/` | NO |

**Action:** Include validated copies in NuGraph repo at `scripts/sbnd/unified-production/configs/fcl/` (SHA-verified byte-identical copies)

---

## Parameterization Changes Made Before Commit

To allow Haiwang to set his own workspace paths without editing source files, the following env var defaults were added:

| Variable | Purpose | Default |
|---------|---------|---------|
| `NUGRAPH_WORKSPACE_DIR` | WCT/larwirecell/opt/mrb-dev root | Avinay's `haiwang-current/` |
| `NUGRAPH_NUML_PY` | Python interpreter for receiver | Avinay's conda numl env |
| `NUGRAPH_RECEIVER` | Path to run_canonical_receiver.py | Repo-relative: `scripts/sbnd/run_canonical_receiver.py` |
| `NUGRAPH_PYWCML_DIR` | NuGraph repo root for PYTHONPATH | Mode-specific defaults (nugraph / nugraph-sophia-dev) |
| `NUGRAPH_DATA_FCL_DIR` | Data FCL directory | NC-sideband validated path |

These defaults preserve full backward compatibility with Avinay's validated runs. Haiwang overrides them to point to his own workspace.

---

## Summary

| Component | Status | SHA / Commit |
|-----------|--------|-------------|
| WCT | ✅ CLEAN, PUSHED | bc7f4af9 @ abhatfnal/pr/nugraph4-wct-integration |
| larwirecell | ✅ CLEAN, PUSHED | 9295e2a3 @ abhatfnal/dev-v10_14_02_02 |
| NuGraph pywcml | ✅ CLEAN, PUSHED | a7c8728e @ abhatfnal/feature/nugraph4-beta-sbnd-streaming |
| run_canonical_receiver.py | ✅ ADDED (this commit) | SHA256: cf0f9d65 |
| Unified production driver | ✅ ADDED (this commit) | — |
| Sim FCL | ✅ INCLUDED (this commit) | SHA256: 857af5c3 |
| Data FCL | ✅ INCLUDED (this commit) | SHA256: 0650836f |

All validated source is now represented by immutable pushed commits in `abhatfnal` personal forks. No pushes to Haiwang's upstream repositories.
