# Haiwang Sophia Handoff Release Report
**Date:** 2026-08-20  
**Author:** Avinay Bhat  
**Status:** PARTIAL — S3 PASS (176019), D1 PASS (176020), S1 resubmit in queue (176027); push to abhatfnal pending user action

---

## 1. Final WCT SHA

```
bc7f4af928921ade590166d5993bca083a4278c0
```

Branch: `pr/nugraph4-wct-integration`  
Remote containing HEAD: `abhatfnal/pr/nugraph4-wct-integration`  
GitHub: `https://github.com/abhatfnal/wire-cell-toolkit/tree/pr/nugraph4-wct-integration`

---

## 2. Final larwirecell SHA

```
9295e2a34c32b5f92ad6483b83dd4895a00b4c9b
```

Branch: `dev-v10_14_02_02`  
Remote containing HEAD: `abhatfnal/dev-v10_14_02_02`  
GitHub: `https://github.com/abhatfnal/larwirecell/tree/dev-v10_14_02_02`

---

## 3. Final NuGraph SHA

Base pywcml commit:
```
a7c8728e37795d48f4582b395fac716d0585e3b0
```

Production package commit:
```
838ccab6f3351fceed5d3d04f94939cd925dfadb
```

Branch: `feature/sbnd-unified-production-20260820`  
Remote: `abhatfnal/nugraph` **(push pending — see Section 15)**

---

## 4. Branch names

| Component | Branch |
|-----------|--------|
| WCT | `pr/nugraph4-wct-integration` |
| larwirecell | `dev-v10_14_02_02` |
| NuGraph (pywcml) | `feature/nugraph4-beta-sbnd-streaming` (a7c8728e) |
| NuGraph (production) | `feature/sbnd-unified-production-20260820` (838ccab) |

---

## 5. Personal GitHub remotes

| Component | Remote |
|-----------|--------|
| WCT | `https://github.com/abhatfnal/wire-cell-toolkit.git` |
| larwirecell | `https://github.com/abhatfnal/larwirecell.git` |
| NuGraph | `https://github.com/abhatfnal/nugraph.git` |

---

## 6. Receiver SHA

```
cf0f9d65d96ce4fd3f54851c7f9b31e78dfdb3231f543b362232275141cadeb8
```

Location in repo: `scripts/sbnd/run_canonical_receiver.py` (committed at 838ccab)

---

## 7. Driver SHA

```
3f76ead8555d01d47927b84837cae16b2fe664db8bfad92cad9d605f8a6f28cb
```

Location in repo: `scripts/sbnd/unified-production/bin/run_nugraph_production.sh`

---

## 8. Both FCL full SHAs

| FCL | SHA256 |
|-----|--------|
| `wcls-img-clus-matching-xin-noint.fcl` | `857af5c3a4d0fcdfabcda79fedb96770e38b4cdf9a65fb36bbbe40052fadd39a` |
| `wcls-img-clus-matching-xin-data-noint.fcl` | `0650836f9e04842c4bb9b012eac4bedfffeb70db82cc9d1942af307717c171cb` |

Both FCLs committed to repo at `scripts/sbnd/unified-production/configs/fcl/` as SHA-verified byte-identical copies.

---

## 9. Handoff path

```
/lus/eagle/projects/neutrinoGPU/abhat/sbnd/sample_generation_port/work/haiwang-current/haiwang-sophia-reproduction-handoff/
```

Contents:
- `README.md`
- `SOPHIA_REPRODUCTION_RUNBOOK.md`
- `VALIDATED_RELEASE_MANIFEST.txt`
- `SHA256SUMS`
- `gate-manifests/sim/sim_S1_manifest.csv`
- `gate-manifests/sim/sim_S3_manifest.csv`
- `gate-manifests/data/data_D1_manifest.csv`
- `gate-manifests/data/data_D3_manifest.csv`
- `reports/` (selected key reports)

Old Polaris handoff (preserved):
```
/lus/eagle/projects/neutrinoGPU/abhat/sbnd/sample_generation_port/work/haiwang-current/haiwang-polaris-reproduction-handoff/
```

---

## 10. Clean-room clone and build paths

Clean-room root:
```
/lus/eagle/projects/neutrinoGPU/abhat/sbnd/clustering/haiwang-handoff-cleanroom-20260820/
```

NuGraph clone from committed branch 838ccab:
```
haiwang-handoff-cleanroom-20260820/nugraph-clone/
```

Gate output directories:
```
haiwang-handoff-cleanroom-20260820/gates/S1/
haiwang-handoff-cleanroom-20260820/gates/S3/
haiwang-handoff-cleanroom-20260820/gates/D1/
```

Clean-room dependency on shared compiled infrastructure:
```
NUGRAPH_WORKSPACE_DIR = /lus/eagle/projects/neutrinoGPU/abhat/sbnd/sample_generation_port/work/haiwang-current
```
(Haiwang must set `NUGRAPH_WORKSPACE_DIR` to his own workspace per the runbook)

Clean-room pywcml: fresh NuGraph clone at 838ccab (NOT Avinay's nugraph-sophia-dev dir)

Clean-room FCL (D1): packaged copy in `nugraph-clone/scripts/sbnd/unified-production/configs/fcl/`

---

## 11. S1 result (clean-room)

**PBS job:** 176018 (initial) → 176027 (resubmit)  
**Status:** INITIAL FAILED; RESUBMIT IN QUEUE (2026-08-21)

**176018 failure root cause:** S1 and S3 were scheduled on the same Sophia compute node and both ran `waf install` concurrently in the shared WCT build directory (`wct-ap-yuhw/`). waf's state-save (`os.rename(.wafpickle*.tmp → .wafpickle*)`) raced — S1 lost and exited with `Container exit: 1`. All WCT header/library files installed successfully before the failure; this is a test-infrastructure race, NOT a pipeline bug.

**176027 status as of 2026-08-21 06:35 UTC:** In queue (by-gpu).

Note: S3 clean-room gate (PBS 176019) processed events 1/2728/1, 1/2728/2, 1/2728/3 — including event 1/2728/1 (the same event S1 tests). S3 was **bitwise identical** to the frozen reference for all 6 samples including event 1 (both APAs). This confirms the S1 pipeline result is correct; only the test harness infra (concurrent waf) caused 176018 to fail.

Expected (176027): Exit 0, 1 event (1/2728/1), 2 APA samples — apa0 (4915 sp), apa1 (1843 sp), sp/features=(N,2), no partial file, bitwise identical to frozen reference.

---

## 12. S3 result (clean-room)

**PBS job:** 176019  
**Status:** PASS — 2026-08-21 06:31 UTC  
**Driver exit:** 0  
**H5 SHA256:** `07b333784a2ba671bada56b410fb1212a80075424aa6b068032f03f1c1f1d5d1`  
**H5 size:** 3,964,796 bytes

**Events received:** 3 / 3 expected

| RSE | APA0 sp | APA1 sp | Split | reco_bundle_id_sentinels |
|-----|---------|---------|-------|--------------------------|
| 1/2728/1 | 4915 | 1843 | train | 0 |
| 1/2728/2 | 2817 | 1188 | validation | 0 |
| 1/2728/3 | 2026 | 675 | train | 0 |

**Bitwise comparison vs frozen reference:** IDENTICAL  
All 6 samples in S3 H5 are bitwise identical (field-by-field numpy `array_equal`) to the corresponding samples in the frozen 50-event reference H5 (`d3c1aaef...`). This confirms:
- TrackFitting state-reset works correctly for events 2 and 3
- The clean-room NuGraph clone (838ccab) produces deterministic output
- campaign_id (`haiwang-nugraph4-canonical-v1`) and train/val/test splits preserved

All gates: `.partial PASS`, `absent-file audit PASS`, `sp_conservation OK`, `plane_conservation OK`, `model_facing_shapes OK`.

---

## 13. D1 result (clean-room)

**PBS job:** 176020  
**Status:** PASS — 2026-08-21 06:33 UTC  
**Driver exit:** 0  
**H5 SHA256:** `7f1a174a06864c386db0b9af02f35a1108f0d76faef15258d7b87f8e830e728b`  
**H5 size:** 2,350,356 bytes

**Events received:** 1 / 1 expected

| RSE | APA0 sp | APA1 sp | Split | topology_source | reco_bundle_id_sentinels |
|-----|---------|---------|-------|-----------------|--------------------------|
| 18255/1/114446 | 3387 | 4194 | train | 1 | 0 |

**Key data gates:**
- `reco_bundle_id_sentinels=0`: No -1 reco_bundle_id values — CTPC confirmed ✅
- `sp_conservation OK`: total=7581, apa0=3387, apa1=4194 ✅
- `plane_conservation OK` ✅
- `model_facing_shapes OK` ✅
- `.partial gate (post-run): PASS` ✅
- `Absent-file audit: PASS` ✅

**Packaged FCL test:** `NUGRAPH_DATA_FCL_DIR` pointed to `configs/fcl/` in the clean-room clone (not Avinay's production FCL dir). FCL SHA256 verified at preflight (`0650836f...`) and again at runtime. This confirms the packaged FCL copy in the repo is functional.

**BNBSpillInfo patch:** injected at `gates/D1/runtime/sbnobj_patch/` — required for real SBND data FCL loading, confirmed working.

LAR exit: `exit=0 wall=53s peak_rss=1765340kB`  
`lar loop complete: 0 failed, 1 passed`

---

## 14. Expected 50-event reference SHA

```
d3c1aaefbd6b7b33e2f5ad10f1cf030051003d419f4d43d37d22ae7639cb6a10
```

This is the SHA256 of the frozen 50-event simulation reference H5 at:
```
/lus/eagle/projects/neutrinoGPU/abhat/sbnd/sample_generation_port/reference/
```

Gate S50 (full sim reproduction) should produce an H5 bitwise identical to this file.

---

## 15. Known data exclusions

Events that MUST NOT be used as handoff gates or in production manifests:

| RSE | Reason |
|-----|--------|
| `18255/1/506114` | WCT sig2img crash (non-deterministic SIGSEGV) |
| `18259/1/37112` | WCT sig2img crash (non-deterministic SIGSEGV) |

These events were encountered in the NC-sideband data campaign and excluded from the validated 19-event corrected manifest. They may succeed occasionally but fail non-deterministically.

---

## 16. No-intermediate audit

Prohibited intermediates that must NOT exist at job completion:
- `nugraph.h5` ← ABSENT in all validated runs ✅
- `mabc.zip` ← ABSENT ✅
- `trash-all-apa.tar.gz` ← ABSENT ✅
- `*.npz` ← ABSENT ✅
- `truth*.json` ← ABSENT ✅

Allowed (by design):
- `nointermediate-debug-bee.zip` — produced by `wcls-img-clus-matching-xin-noint.jsonnet` BeeSink (`bee_noint`), expected per design

---

## 17. Environment assumptions

| Assumption | Value | Notes |
|-----------|-------|-------|
| Scheduler | PBS | Sophia PBS; NOT Polaris |
| Queue | `by-gpu` | NOT `debug` |
| Allocation | `neutrinoGPU::wirecell_2026` | NOT `neutrinoGPU::debug` |
| Filesystems | `home:eagle:grand` | Grand for SIF container |
| Container | SLF7 + larsoft v10_14_02 squashfs | Fixed; shared Eagle |
| Module init | `module load spack-pe-base; module load apptainer` | Must run on login + compute |
| Eagle project | `/lus/eagle/projects/neutrinoGPU/` | Shared project space |
| WCT data | Snehadri's spack dir on Eagle | Read-only shared |

---

## 18. Exact message Haiwang should receive

> **Haiwang — Sophia NuGraph4 production handoff is ready.**
>
> Everything is at:
> ```
> /lus/eagle/projects/neutrinoGPU/abhat/sbnd/sample_generation_port/work/haiwang-current/haiwang-sophia-reproduction-handoff/
> ```
> Start with **SOPHIA_REPRODUCTION_RUNBOOK.md**.
>
> **Frozen source:**
> - WCT: `bc7f4af9` → `abhatfnal/wire-cell-toolkit` branch `pr/nugraph4-wct-integration`
> - larwirecell: `9295e2a3` → `abhatfnal/larwirecell` branch `dev-v10_14_02_02`
> - NuGraph (pywcml + driver): `838ccab` → `abhatfnal/nugraph` branch `feature/sbnd-unified-production-20260820`
>
> **Run the gates in order:** S1 → S3 → S50 (sim); D1 → D3 (data).
> Do NOT skip S3 — it validates TrackFitting state reset for multi-event runs.
>
> **Known bad events** (never use): `18255/1/506114` and `18259/1/37112` (WCT sig2img crashes).
>
> The single driver entry point is:
> ```bash
> bash run_nugraph_production.sh --mode sim|data --manifest ... --output-h5 ... --output-dir ...
> ```
>
> Let me know when S1 passes and we'll move to S50.

---

## Final Verdict

**PARTIAL** — Awaiting:
1. GitHub push of `feature/sbnd-unified-production-20260820` to `abhatfnal/nugraph` (requires interactive auth; user must run: `git push abhatfnal feature/sbnd-unified-production-20260820` from Sophia login node with GitHub token configured)
2. S1 clean-room resubmit (PBS 176027) result — in queue as of 2026-08-21 06:35 UTC

**CONFIRMED COMPLETE (2026-08-21):**
- S3 clean-room: PASS — bitwise identical to frozen reference (PBS 176019, 06:31 UTC)
- D1 clean-room: PASS — CTPC confirmed, packaged FCL validated (PBS 176020, 06:33 UTC)
- S1 pipeline correctness: CONFIRMED via S3 event 1 comparison — bitwise match to frozen reference

S1 initial job (176018) failed due to a test-infrastructure race (concurrent waf build on same node as S3), not a pipeline bug. Resubmit 176027 in queue; result expected to PASS.

Once the push succeeds and PBS 176027 exits 0, verdict upgrades to:

**PASS — SOPHIA-FIRST UNIFIED NUGRAPH PRODUCTION HANDOFF: FROZEN, COMMITTED, PUSHED, AND CLEAN-ROOM VALIDATED**

Gates confirmed to date:
| Gate | PBS | Result | Note |
|------|-----|--------|------|
| S3 (sim 3-event) | 176019 | **PASS** | Bitwise identical to frozen reference; TrackFitting state-reset confirmed |
| D1 (data 1-event) | 176020 | **PASS** | CTPC, packaged FCL, BNBSpillInfo patch |
| S1 (sim 1-event) | 176027 | PENDING | In queue; pipeline correctness confirmed via S3 event 1 |
