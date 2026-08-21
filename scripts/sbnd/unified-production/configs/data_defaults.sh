#!/bin/bash
# Mode-specific frozen config for --mode data.
# All SHA values verified against 19-event corrected run (PBS 175910, PASS 2026-08-20).

NUGRAPH_MODE=data

# Frozen source commits
NUGRAPH_WCT_COMMIT=bc7f4af9
NUGRAPH_LWC_COMMIT=9295e2a3

# Frozen FCL (do NOT copy; reference by absolute path)
NUGRAPH_FCL_DIR=/lus/eagle/projects/neutrinoGPU/abhat/sbnd/clustering/engineering-nc-sideband-19evt-new-pipeline/scripts/19event_run_v1
NUGRAPH_FCL_NAME=wcls-img-clus-matching-xin-data-noint.fcl
NUGRAPH_FCL_SHA=0650836f9e04842c4bb9b012eac4bedfffeb70db82cc9d1942af307717c171cb

# pywcml directory (contains nugraph-sophia-dev build)
# Override by setting NUGRAPH_PYWCML_DIR to your NuGraph repo clone root.
NUGRAPH_PYWCML_DIR="${NUGRAPH_PYWCML_DIR:-/lus/eagle/projects/neutrinoGPU/abhat/sbnd/clustering/nugraph-sophia-dev}"

# PBS settings
NUGRAPH_PBS_QUEUE=by-gpu
NUGRAPH_PBS_ACCOUNT=neutrinoGPU::wirecell_2026
NUGRAPH_PBS_WALLTIME=02:30:00

# Receiver settings: data runs one lar session per event; max-sessions = nrow(receiver manifest)
NUGRAPH_RECEIVER_TIMEOUT=900
NUGRAPH_RECEIVER_INTER_SESSION_TIMEOUT=600

# Container script (data-specific steps: larwirecell + BNBSpillInfo patch + N lar sessions)
NUGRAPH_CONTAINER_SCRIPT_NAME=run_data_container.sh
