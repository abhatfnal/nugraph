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
- Projects truth from `ionandscint:priorSCE` (simulation) or equivalent data truth
- H5 hook enabled
- Provides semantic/instance ground truth for training

### labeler_tagger

- Runs **after** PR
- `label_blobs=false`
- Tagger/BEE role
- Not a second full truth-projection stage

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
