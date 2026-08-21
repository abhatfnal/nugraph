#!/bin/bash
# Mode-specific frozen config for --mode sim.
# All SHA values verified against 50-event gate-closed run (PBS 7446816, PASS 2026-08-13).

NUGRAPH_MODE=sim

# Frozen source commits
# NOTE: The Aug 13 engineering run declared 0869668/6ead889 by git HEAD, but
# the effective compiled state was bc7f4af9/9295e2a3 (working-tree modifications
# that were later committed). See SIM_SOURCE_STATE_INTEGRITY_AUDIT_2026-08-20.md.
NUGRAPH_WCT_COMMIT=bc7f4af9
NUGRAPH_LWC_COMMIT=9295e2a3

# Frozen FCL
NUGRAPH_FCL_NAME=wcls-img-clus-matching-xin-noint.fcl
NUGRAPH_FCL_SHA=857af5c3a4d0fcdfabcda79fedb96770e38b4cdf9a65fb36bbbe40052fadd39a

# pywcml directory (contains nugraph package and pywcml)
# Override by setting NUGRAPH_PYWCML_DIR to your NuGraph repo clone root.
NUGRAPH_PYWCML_DIR="${NUGRAPH_PYWCML_DIR:-/lus/eagle/projects/neutrinoGPU/abhat/sbnd/clustering/nugraph}"

# PBS settings (Sophia: by-gpu queue; original Polaris run used 'debug' queue which does not exist here)
NUGRAPH_PBS_QUEUE=by-gpu
NUGRAPH_PBS_ACCOUNT=neutrinoGPU::wirecell_2026
NUGRAPH_PBS_WALLTIME=01:30:00

# Receiver settings: sim runs all events in one lar session
NUGRAPH_RECEIVER_TIMEOUT=480
NUGRAPH_RECEIVER_INTER_SESSION_TIMEOUT=300

# Container script (sim-specific steps: WCT waf rebuild + doctest + larwirecell + 1 lar session)
NUGRAPH_CONTAINER_SCRIPT_NAME=run_sim_container.sh
