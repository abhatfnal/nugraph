# Sim Source-State Integrity Audit
**Date:** 2026-08-20  
**Purpose:** Phase 7.5 — determine whether the validated 50-event simulation run (PBS 7446816, PASS 2026-08-13) depended on committed-only source at the declared SHA values, or on uncommitted working-tree modifications.

---

## Executive Summary

**VERDICT: CORRECTION IDENTIFIED, AUTHORIZED, AND APPLIED (2026-08-20)**

**Correction applied:** `sim_defaults.sh` and `lib/containers/run_sim_container.sh` updated to declare `bc7f4af9` / `9295e2a3`. Sim dry-run PASS confirmed. Sim one-event regression submitted as PBS 175962.

The simulation PBS scripts declared frozen source states `WCT=0869668` and `larwirecell=6ead889`. Both declarations are underdescriptions. The validated 50-event run compiled:

1. **WCT:** Commit `0869668` PLUS two working-tree patches to `TrackFitting.cxx` and `TaggerCheckSTM.cxx` that were applied by the container script before `waf install`. These patches were subsequently committed at `983495f` (fix) and `9b1379e` (test), which were then merged into `bc7f4af9` (current HEAD).

2. **larwirecell:** Commit `6ead889` PLUS an uncommitted working-tree file `EventGraphIPC.cxx` (7186 bytes) that provided the IPC producer needed by the no-intermediate pipeline. This file was subsequently committed at `9295e2a3` (one commit past `6ead889`, current HEAD).

The current source trees are at `WCT=bc7f4af9` and `larwirecell=9295e2a3`. The production-critical source files (TrackFitting.cxx, TaggerCheckSTM.cxx, EventGraphIPC.cxx) in the current trees are byte-equivalent to what was compiled in the validated run. The two repos were NOT clean at run time; they were at 0869668/6ead889 by `git rev-parse HEAD` but carried uncommitted modifications that the PBS gate did not detect.

---

## Detailed Findings

### Finding 1: WCT working-tree patch (required for valid multi-event sim)

**What 0869668 lacks:** The `clear_segments()` function exists at commit `0869668` but has only the original data-structure clears. It does NOT clear `m_grouping`, `wpid_geoms`, `wpid_offsets`, `wpid_slopes`, `wpid_params`, `wpid_U_dir/V_dir/W_dir`, `apas`, `m_hot_cache`, or `global_rb_map`. Without these resets, `TaggerCheckSTM::search_other_tracks()` on event 2+ retains a dangling pointer to the previous event's freed `Grouping`, causing a SIGSEGV.

**The patch applied by the container script (from PBS log SHA256-verified section):**

```diff
diff --git a/clus/src/TrackFitting.cxx b/clus/src/TrackFitting.cxx
index 46c7e13..bef1da9 100644
--- a/clus/src/TrackFitting.cxx
+++ b/clus/src/TrackFitting.cxx
@@ -270,6 +270,31 @@ void TrackFitting::clear_segments(){
     m_cluster_charge_data.clear();
     m_cluster_fitted_charge_2d.clear();
     m_fitted_charge_2d.clear();
+
+    // Reset grouping and all geometry derived from it
+    m_grouping = nullptr;
+    wpid_geoms.clear();   wpid_offsets.clear();  wpid_slopes.clear();
+    wpid_params.clear();  wpid_U_dir.clear();    wpid_V_dir.clear();
+    wpid_W_dir.clear();   apas.clear();          m_hot_cache.clear();
+
+    // Clear the global readout-blob map
+    global_rb_map.clear();
 }
```

```diff
diff --git a/clus/src/TaggerCheckSTM.cxx b/clus/src/TaggerCheckSTM.cxx
index 287a3b8..374ca22 100644
--- a/clus/src/TaggerCheckSTM.cxx
+++ b/clus/src/TaggerCheckSTM.cxx
@@ -2484,7 +2484,15 @@ private:
         const size_t N = x_coords.size();
         if (N == 0) return;

+        // Reset m_grouping so next event re-drives BuildGeometry() from the
+        // CURRENT event's live Grouping. Without this, m_grouping retains a
+        // dangling pointer to the previous event's freed Grouping, causing
+        // SIGSEGV inside do_single_tracking() on event ≥2.
+        m_track_fitter.clear_segments();
+
         std::vector<bool> flag_tagged(N, false);
```

**SHA256 cross-check of production source files:**

| File | Compiled at run time (from PBS log) | Current working tree | Match |
|------|--------------------------------------|----------------------|-------|
| `TrackFitting.cxx` | `d892fdb9...` | `d892fdb9...` | **YES** |
| `TaggerCheckSTM.cxx` | `f7af9073...` | `f7af9073...` | **YES** |
| `doctest_trackfitting_clear_segments.cxx` | `fb1c7cae...` | `6d147183...` | NO (test-only) |

The doctest SHA mismatch is in test-only code (not linked into `libWireCellClus.so`). It does not affect physics output validity. The production source files are byte-identical.

**Commits that incorporate this fix:**
- `983495f` — "fix(clus): reset TrackFitting state between events" — committed the production fix
- `9b1379e` — "test(clus): add regression for TrackFitting event-state reset" — committed the updated doctest
- `bc7f4af9` (HEAD, current) — merge commit pulling both `983495f` and `9b1379e` into `pr/nugraph4-wct-integration`

---

### Finding 2: larwirecell EventGraphIPC.cxx absent from 6ead889

**What 6ead889 lacks:** `EventGraphIPC.cxx` (7186 bytes) does not exist in the committed tree at `6ead889`. Confirmed by:

```
git show 6ead889:larwirecell/aiml/EventGraphIPC.cxx
fatal: path 'larwirecell/aiml/EventGraphIPC.cxx' exists on disk, but not in '6ead889'
```

Without this file, a clean checkout at `6ead889` would either fail to compile (CMakeLists already includes it) or produce `libWireCellAIML.so` without IPC support. Either way the receiver socket would never receive data.

**How the validated run succeeded:** At the time of PBS 7446816 (2026-08-13), `EventGraphIPC.cxx` existed as an uncommitted working-tree file. The cmake incremental build compiled it because CMakeLists.txt was already wired for it. The PBS gate checked only `git rev-parse HEAD` (= `6ead889`, MATCH) and did not detect the uncommitted file.

**Commit that formalizes this:**
- `9295e2a3` (current HEAD) — "feat(aiml): stream EventGraph over IPC without HDF5 handoff" — committed `EventGraphIPC.cxx` one step past `6ead889`

```
git log --oneline larwirecell/aiml/EventGraphIPC.cxx
9295e2a feat(aiml): stream EventGraph over IPC without HDF5 handoff
```

---

## Current State of Both Trees

| Repo | Current HEAD | State |
|------|-------------|-------|
| `wct-ap-yuhw` | `bc7f4af9` | Clean (only 1 untracked core dump) |
| `larwirecell-dev` | `9295e2a3` | Clean (only 2 untracked core dumps) |

Both trees are currently clean. The working-tree modifications that were present during the Aug 13 run have since been committed into the current HEAD commits.

---

## Answers to the 7 Questions

1. **Was the TrackFitting/clear_segments fix in 0869668?**  
   NO. Present as function declaration only; the extended body (geometry map resets + global_rb_map.clear()) was absent. Applied as working-tree patch by the container script.

2. **What exact diff was applied?**  
   The two-file diff shown above in Finding 1, also embedded verbatim in the 50-event PBS log. SHA256-verifiable from the logged source hashes.

3. **Was the working tree dirty at the time of the successful run?**  
   YES. Both repos were dirty in production-critical ways: WCT had patched TrackFitting.cxx and TaggerCheckSTM.cxx; larwirecell had an uncommitted EventGraphIPC.cxx.

4. **Is the current WCT tree byte/source-equivalent to what was compiled?**  
   YES for production files (TrackFitting.cxx ✓, TaggerCheckSTM.cxx ✓). NO for the doctest file (test-only; does not affect physics).

5. **Does larwirecell 6ead889 contain EventGraphIPC.cxx?**  
   NO. Absent from the committed tree at that SHA.

6. **Where did the IPC implementation come from in the successful run?**  
   From an uncommitted working-tree file present on disk at `larwirecell-dev/larwirecell/aiml/EventGraphIPC.cxx`. Compiled by cmake because CMakeLists.txt was pre-wired for it.

7. **Is sim_defaults.sh (WCT=0869668, lwc=6ead889) sufficient to reproduce the validated pipeline from a clean checkout?**  
   **NO.** A clean checkout at those SHAs fails in two distinct ways:
   - WCT at 0869668: SIGSEGV on event 2 (TrackFitting reset not committed)
   - larwirecell at 6ead889: compile or link failure (EventGraphIPC.cxx absent)

---

## Required Correction (DO NOT APPLY WITHOUT EXPLICIT USER AUTHORIZATION)

The only change needed is to the SHA gate values in `sim_defaults.sh` and `lib/containers/run_sim_container.sh`. No source code changes; the fix is already committed.

**Proposed new declarations:**

| Field | Current (wrong) | Proposed (correct) |
|-------|-----------------|-------------------|
| `NUGRAPH_WCT_COMMIT` in `sim_defaults.sh` | `0869668` | `bc7f4af9` |
| `NUGRAPH_LWC_COMMIT` in `sim_defaults.sh` | `6ead889` | `9295e2a3` |
| WCT SHA gate in `run_sim_container.sh` | `0869668*` | `bc7f4af9*` |
| larwirecell SHA gate in `run_sim_container.sh` | `6ead889*` | `9295e2a3*` |

Note: `bc7f4af9` is the current HEAD of `wct-ap-yuhw` and already the declared frozen SHA for the data path. `9295e2a3` is the current HEAD of `larwirecell-dev` and already the declared frozen SHA for the data path. After the correction both modes would use the same WCT and larwirecell commits, which is correct: the data path was always run against the fully committed state.

The WCT waf rebuild step in the sim container remains necessary and correct: even with the fix committed at `bc7f4af9`, the installed libs in `$OPT/lib/` may be stale from an earlier build and must be rebuilt.

**No source code changes needed. Do not alter any WCT or larwirecell source files.**

---

## Impact on Validated References

This correction has **no impact** on:
- The frozen 50-event sim reference H5 (SHA `d3c1aaef...`): compiled from equivalent source
- The data pipeline (already at `bc7f4af9/9295e2a3`): unaffected
- Any previously produced H5 files or BEE artifacts

**Correction applied and authorized 2026-08-20. The unified pipeline now references the committed source state equivalent to the code actually compiled in the validated simulation workflow.**

The unified pipeline now references the committed source state equivalent to
the code actually compiled in the validated simulation workflow.

Additional note: The sim PBS queue on Sophia is `by-gpu` / `neutrinoGPU::wirecell_2026` (not `debug`, which was the Polaris queue). `sim_defaults.sh` updated accordingly.
