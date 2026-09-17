# NuGraph Development Handoff — 2026-09-16

**Author:** abhat@uchicago.edu

**Repo:** https://github.com/abhatfnal/nugraph

**Branch:** `feature/sbnd-unified-production-20260820`

**Date:** 2026-09-16

This document records the validated state of the Sophia/Polaris NuGraph development implementation at the point of handoff to a separate development session. It is a freeze-point reference, not a how-to guide.

---

## Architecture

Haiwang reconstruction everywhere; our enhanced NuGraph H5 at the output boundary.

```
Reco1
  → Haiwang integrated one-step WCT
  → truth TensorSetLabeler (labeler_truth)
  → complete PR/tagger/tracking
  → tagger TensorSetLabeler (labeler_tagger)
  → enhanced raw NuGraph H5
  → canonical per-APA NuGraph H5
```

---

## NuGraph Repository Anchors

| Label | SHA |
|-------|-----|
| validated production ancestor | `838ccab6` |
| receiver commit | `cf0f9d65` |
| previous release/docs tip | `eada56e` |
| remote tip before this session | `ac31bf1f` |

---

## Integrated WCT / LArWireCell Anchors

| Component | Commit |
|-----------|--------|
| integrated WCT | `b2e3c6a9b440af9f440151d5e9c9aa1771194bd0` |
| integrated larwirecell | `5c50b2dc31a8b8f07b4afe4e1987884e2f298901` |

**Haiwang source lineage:**

| Component | Commit |
|-----------|--------|
| WCT | `609dea85eff1a3e547aeefa29bb1b46871682da3` |
| larwirecell | `a02a1a4d84910032fd8c99cda496dd054c65a01b` |

---

## Validated Enhanced H5 Contract

### Required fields

- `sp/reco_bundle_id`
- `sp/reco_segment_id`
- `sp/apa`
- `sp/face`
- `metadata/sp_topology_source`

### Semantics

- `topology_source = 1` → CTPC reconstruction-native topology
- `topology_source = 2` → KNN fallback; fallback samples must be quarantined

### Invariants

- `features[:,1] == reco_segment_id` — do NOT rename `features[:,1]` to `real_cluster_id`
- `sp/edge_label_index == sp_nexus_sp/edge_index` — required for correct edge supervision

### Canonical converter

One raw compound event → two per-APA NuGraph samples.

---

## Two TensorSetLabelers

### labeler_truth

- Runs **before** PR
- `label_blobs=true`
- Owns truth projection/write-back from `ionandscint:priorSCE` in simulation; truth/BEE
  sets as configured
- **H5 output OFF** — does NOT own the enhanced NuGraph H5
- Provides semantic/instance ground truth for downstream labeler_tagger to observe

### labeler_tagger

- Runs **after** the complete 15-stage PR/tagger/tracking chain
- `label_blobs=false` — preserves the truth labels written upstream
- Tagger/BEE role; observes post-PR `reco_segment_id`
- **Sole enhanced NuGraph H5 writer** — reads preserved `matching_bundle_id` and
  serializes it as `sp/reco_bundle_id` (non-negative for all SPs)
- H5 written here ensures `sp/reco_bundle_id` reflects `stamp_matching_bundle_id`
  provenance from `clus_pr`, not the pre-PR −1 sentinel

---

## PR Chain — 15 Configured Stage Occurrences

Do not reduce this count to "13" merely because some stage types repeat.

| # | Stage type |
|---|-----------|
| 1 | switch_scope |
| 2 | unmerge_bundle |
| 3 | unmerge_assoc |
| 4 | steiner |
| 5 | fiducialutils |
| 6 | tagger_check_tgm |
| 7 | tagger_check_stm |
| 8 | tagger_check_fc |
| 9 | protect_bundle |
| 10 | steiner_refresh |
| 11 | tagger_check_neutrino |
| 12 | numu_bdt_scorer |
| 13 | nue_bdt_scorer |
| 14 | tracking_visitor |
| 15 | tagger_output |

---

## RSE Propagation

Keep the two RSE paths distinct:

- **H5:** TensorSetLabeler reads run/subrun/event directly from ART Event
- **PR/MABC/tracking:** TensorSetMetadataAttacher + `rse_from_metadata`

Do not mix these paths.

---

## Validated Results

### Observer-neutrality validation

```
FULL_HAIWANG_1STEP_PLUS_ENHANCED_NUGRAPH_TRACKFITTING_OBSERVER_NEUTRALITY_PASS
ENHANCED_NUGRAPH_RAW_AND_CANONICAL_CONTRACT_PASS
```

### Frozen 5-event reconstruction (real BNB-on data)

```
FROZEN_5EVENT_HAIWANG_PLUS_ENHANCED_NUGRAPH_PRODUCTION_VALIDATION_PASS
```

| RSE | SP count |
|-----|---------|
| 1/0/2 | 5135 |
| 1/0/3 | 2658 |
| 1/0/5 | 5767 |
| 1/0/6 | 2267 |
| 1/0/8 | 5765 |

All events: `topology_source = 1`, canonical = 10/10 APA samples.

### Full one-event simulation validation

```
FULL_SBND_SIM_GEN_TO_ENHANCED_NUGRAPH_1EVENT_PASS
SIM_TRUTH_PRIORSCE_TO_TENSORSETLABELER_PASS
HAIWANG_FULL_15_STAGE_RECONSTRUCTION_PASS
ENHANCED_NUGRAPH_RAW_AND_CANONICAL_CONTRACT_PASS
```

Validated raw H5 example (RSE 1/0/1):
- 5048 spacepoints, 11980 edges
- `topology_source = 1`
- semantic: `{-1: 528, 0: 44, 1: 4476}`

---

## Important Historical Behaviors

### DL mode fallback

`HAIWANG_19EVENT_DL_MODE=GEOMETRIC_FALLBACK`

42 XML BDT files were copied and verified byte-identical. The final nue XGBoost model was historically absent; the official configuration warns and skips it (expected behavior, not a bug).

### tracking-pr.root filename collision

`tracking-pr.root` is a fixed output filename. Production must run each event in its own isolated working directory (`wct/evt-{N}/`) to prevent overwrite collisions.

### Simulation truth

For simulation validation, ART truth used is `ionandscint:priorSCE` through TensorSetLabeler. Old CellTree-derived labeling produced charge-like pathological truth labels and must not be reintroduced.

### priorSCE propagation

`sim::SimEnergyDeposits_ionandscint_priorSCE_G4` must be preserved through DetSim and Reco1 using custom wrapper FCLs that add:
```
keep sim::SimEnergyDeposits_ionandscint_priorSCE_*
```
to `outputCommands`.

---

## Platform Boundary

This document records the validated Sophia/Polaris implementation.

Aurora production and current Gen-2 generation work are handled in a separate session and project. Do not merge Aurora production experimentation into this branch unless explicitly requested.

---

## Runtime Freeze (Sophia PBS 185534)

| Component | Version |
|-----------|---------|
| Container | `/lus/grand/projects/neutrinoGPU/software/containers/slf7.sif` |
| sbndcode | v10_14_02_04 |
| larsoft squashfs | `/lus/eagle/projects/neutrinoGPU/larsoft_hpc/images/larsoft-v10_14_02.squashfs` |
| sbnd delta | `/lus/eagle/projects/neutrinoGPU/larsoft_hpc/images/sbnd-v10_14_02_04_delta.squashfs` |
| libWireCellAIML.so | `ceac0bd8c911e33f31d5a50db5566312469738cecf179aee94489c68b2d8047a` |
| libWireCellLarsoft.so | `eede765676664b10c5827435d6a79bf83361d8ee0e4f7b814641d26adab9871c` |
| libWireCellAux.so | `fc3f509662d6919b030a7557fedc815c8e08c90320c1e89eabae27df70ec899d` |

**Library path note:** `libWireCellAux.so` lives in `build/opt/lib/`, NOT `build/lwc-install/lib/`. AIML and Larsoft libs are in `build/lwc-install/lib/`.

**WIRECELL_PATH must include:**
```
$CFGDIR:$INTDIR/wct/cfg:$INTDIR/wct-data:$INTDIR/wire-cell-data-official:${WIRECELL_PATH:-}
```
`wire-cell-data-official/` contains `sbnd-wires-geometry-v0206.json.bz2` which `WireSchemaFile` resolves by name via WIRECELL_PATH search. Omitting it causes a crash at WCT startup.

---

## reco_bundle_id Fix — 2026-09-17

### Root cause

`labeler_truth` (the truth/SED TensorSetLabeler) owned the `nugraph.h5` write in the
two-labeler integration architecture. It runs **before** `clus_pr`, so at write time all
`sp/reco_bundle_id` values are still −1 (MABC has not yet stamped the coarse bundle IDs).

### Call chain

```
clus_all_apa → labeler_truth (H5 write, pre-PR) → clus_pr (stamp_matching_bundle_id) → ...
```

`MultiAlgBlobClustering::execute()` stamps `matching_bundle_id` into every cluster's
perblob PC at line 2509 (`clus_pr`), **after** `labeler_truth` has already written the H5.
`matching_bundle_id` survives PR cluster splits via `ClusteringSwitchScope::carry_anames`
(hardcoded field list, `clustering_switch_scope.cxx` line 99) and `ClusteringUnmergeBundle`
via `Dataset::subset` in `carve()`.

### Final architecture

```
clus_all_apa → labeler_truth (label_blobs=true, H5 OFF)
             → clus_pr (stamp_matching_bundle_id=true, 15-stage PR/tagger/tracking)
             → labeler_tagger (label_blobs=false, H5 ON → nugraph.h5)
```

`labeler_tagger` is the sole `nugraph.h5` writer. All SPs get a non-negative
`reco_bundle_id` because stamping completes before the H5 is written.

For the **single-labeler** `wcp-porting` architecture the fix reduces to:
- `stamp_matching_bundle_id=true` in `clus_maker.pr()` call (already present since commit
  `f0321d8`, 2026-08-11)
- `hdf5_output: enable_nugraph_h5` on the single post-PR labeler (Phase E, 2026-09-17)

### Canonical source changes

| Repo | Branch | File | Change |
|------|--------|------|--------|
| `wcp-porting` (`abhatfnal/wcp-porting-validation`) | `checkpoint/validated-dual-output-2026-09-08` | `sbnd/wcls-img-clus-matching-xin.jsonnet` | Add `enable_nugraph_h5` extVar; add `hdf5_output: enable_nugraph_h5` to post-PR labeler |

`pr-operating-point.jsonnet` has no canonical git-tracked source. The `wcp-porting`
single-labeler chain calls `clus_maker.pr()` directly and does not route through it.
The config-final version (validation evidence in
`reco-bundle-id-fix-validation-20260916/config-final/`) adds `stamp_matching_bundle_id`
as a param; that change lives only in the validation artifact, not a tracked repository.

### Five-event acceptance results (PBS 186546, 2026-09-17)

| RSE | n_sp | APA0 | APA1 | reco_bundle_id ≥ 0 |
|-----|------|------|------|----------------------|
| 1/0/2 | 5135 | 2320 | 2815 | 0 negative |
| 1/0/3 | 2658 | 306 | 2352 | 0 negative |
| 1/0/5 | 5767 | 2199 | 3568 | 0 negative |
| 1/0/6 | 2267 | 1528 | 739 | 0 negative |
| 1/0/8 | 5765 | 2595 | 3170 | 0 negative |

All events: topology = CTPC, 15/15 PR stages, INV1 and INV2 pass, per-segment uniformity
(all `reco_segment_id` clusters have uniform `reco_bundle_id`), physical SP key 1:1 match
vs pre-PR (RSE 1/0/2).

### Actual canonical NuGraph adapter result

Adapter: `pywcml.adapt_tsl.read_tsl_event()` + `build_apa_graph()` from nugraph repo
`a7c8728e37795d48f4582b395fac716d0585e3b0` (adapt_tsl.py `43c3b3a`), env `nugraph-a-sophia`.
Written via `StreamingH5Writer.append_event(identity, apa0, apa1)`, read back via
`NuGraphData.load(dset)`.

- 5 raw events → 10/10 APA samples written and finalized
- All 10 NuGraphData round-trips: `reco_bundle_id ≥ 0`, `reco_segment_id` preserved,
  `features[:,1] == reco_segment_id`
- No `TopologyGateError` (all CTPC)

### Bundle→segment provenance semantics

`reco_bundle_id` = coarse flash-bundle identity from `stamp_matching_bundle_id` (one ID
per MABC input cluster, 13–20 per event). Survives PR cluster splits and is uniform within
each post-PR `reco_segment_id` cluster (fine, reconstructed grouping). `reco_bundle_id`
serves as the coarse Q/L-window grouping for NuGraph4 training; `reco_segment_id` is the
fine post-PR cluster index. These are distinct: a bundle can contain many segments; a
segment cannot span bundles.

`y_instance` is the truth particle ID and is intentionally NOT used for uniformity checks
since truth particles can cross flash-bundle boundaries.

### Verdict

`RECO_BUNDLE_ID_PROVENANCE_PASS` (2026-09-17)
