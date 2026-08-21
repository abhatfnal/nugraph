#!/bin/bash
# Common functions for unified NuGraph production driver.
# Source this file; do not execute directly.
#
# All validated SHA values and paths are documented in:
#   reports/UNIFIED_PIPELINE_EXISTING_WORKFLOW_AUDIT_2026-08-20.md
#
# CONFIGURABLE ENV VARS (set before sourcing or before running driver):
#   NUGRAPH_WORKSPACE_DIR   — WCT/larwirecell workspace root (contains wct-ap-yuhw/, larwirecell-dev/, opt/, etc.)
#   NUGRAPH_NUML_PY         — path to Python interpreter with nugraph/pywcml packages
#   NUGRAPH_RECEIVER        — path to run_canonical_receiver.py (default: auto-detected from driver location)
#   NUGRAPH_PYWCML_DIR      — path to NuGraph repo root (for PYTHONPATH; set in *_defaults.sh)
#
# See SOPHIA_REPRODUCTION_RUNBOOK.md for workspace setup instructions.

# ─────────────────────────────────────────────────────────────────────────────
# Unified driver location (auto-detected; relative to this file)
# ─────────────────────────────────────────────────────────────────────────────
NUGRAPH_DRIVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ─────────────────────────────────────────────────────────────────────────────
# System paths (shared Eagle resources — common to all Sophia users)
# ─────────────────────────────────────────────────────────────────────────────
NUGRAPH_IMAGES=/lus/eagle/projects/neutrinoGPU/larsoft_hpc/images
NUGRAPH_SIF=/lus/grand/projects/neutrinoGPU/software/containers/slf7.sif
NUGRAPH_LARSOFT_SQS=$NUGRAPH_IMAGES/larsoft-v10_14_02.squashfs
NUGRAPH_SBND_DELTA_SQS=$NUGRAPH_IMAGES/sbnd-v10_14_02_04_delta.squashfs

# ─────────────────────────────────────────────────────────────────────────────
# User-specific paths (override via env vars for a different workspace)
# ─────────────────────────────────────────────────────────────────────────────
# NUGRAPH_WORKSPACE_DIR: root of the WCT/larwirecell/mrb-dev compiled workspace.
# Must contain: wct-ap-yuhw/, larwirecell-dev/, opt/, mrb-dev/, wcp-porting/sbnd/
# Set this to YOUR workspace directory (not Avinay's) when running as Haiwang.
NUGRAPH_WORKSPACE_DIR="${NUGRAPH_WORKSPACE_DIR:-/lus/eagle/projects/neutrinoGPU/abhat/sbnd/sample_generation_port/work/haiwang-current}"
NUGRAPH_BASE="$NUGRAPH_WORKSPACE_DIR"

# Python interpreter for the receiver (must have nugraph/pywcml packages installed).
NUGRAPH_NUML_PY="${NUGRAPH_NUML_PY:-/lus/eagle/projects/neutrinoGPU/abhat/conda/envs/numl/bin/python}"

# Canonical receiver script.
# Default: repo-relative path (scripts/sbnd/run_canonical_receiver.py, one level above driver root)
NUGRAPH_RECEIVER="${NUGRAPH_RECEIVER:-$NUGRAPH_DRIVER_DIR/../run_canonical_receiver.py}"

# Frozen receiver SHA
NUGRAPH_RECEIVER_SHA="cf0f9d65"

# ─────────────────────────────────────────────────────────────────────────────
# check_receiver_sha — abort if receiver is not at frozen SHA
# ─────────────────────────────────────────────────────────────────────────────
check_receiver_sha() {
    local log="${1:-/dev/stderr}"
    local actual
    actual=$(sha256sum "$NUGRAPH_RECEIVER" 2>/dev/null | awk '{print $1}')
    echo "Receiver SHA256: $actual" | tee -a "$log"
    if [[ "$actual" != ${NUGRAPH_RECEIVER_SHA}* ]]; then
        echo "PREFLIGHT FAIL: receiver SHA mismatch (expected ${NUGRAPH_RECEIVER_SHA}*, got $actual)" | tee -a "$log"
        return 1
    fi
    echo "Receiver SHA gate: PASS" | tee -a "$log"
}

# ─────────────────────────────────────────────────────────────────────────────
# check_no_partial — abort if a .partial file exists for the output H5
# ─────────────────────────────────────────────────────────────────────────────
check_no_partial() {
    local output_h5="$1"
    local log="${2:-/dev/stderr}"
    if ls "${output_h5}.partial" 2>/dev/null | grep -q .; then
        echo "PREFLIGHT FAIL: .partial file exists for $output_h5 — prior run may not have finalized cleanly" | tee -a "$log"
        return 1
    fi
    echo ".partial gate: PASS" | tee -a "$log"
}

# ─────────────────────────────────────────────────────────────────────────────
# check_output_no_collision — abort if output H5 already exists
# ─────────────────────────────────────────────────────────────────────────────
check_output_no_collision() {
    local output_h5="$1"
    local log="${2:-/dev/stderr}"
    if [ -f "$output_h5" ]; then
        echo "PREFLIGHT FAIL: output H5 already exists: $output_h5" | tee -a "$log"
        echo "  Delete or rename before re-running." | tee -a "$log"
        return 1
    fi
    echo "Output collision check: PASS (no pre-existing H5)" | tee -a "$log"
}

# ─────────────────────────────────────────────────────────────────────────────
# check_absent_files — confirm banned intermediate files are absent under DIR
# ─────────────────────────────────────────────────────────────────────────────
check_absent_files() {
    local dir="$1"
    local log="${2:-/dev/stderr}"
    local BANNED=("nugraph.h5" "mabc.zip" "trash-all-apa.tar.gz")
    local found=0
    for pattern in "${BANNED[@]}"; do
        local hits
        hits=$(find "$dir" -name "$pattern" 2>/dev/null | head -5)
        if [ -n "$hits" ]; then
            echo "ABSENT-FILE FAIL: found $pattern under $dir:" | tee -a "$log"
            echo "$hits" | tee -a "$log"
            found=1
        fi
    done
    if find "$dir" -name '*.npz' 2>/dev/null | grep -q .; then
        echo "ABSENT-FILE FAIL: *.npz files found under $dir" | tee -a "$log"
        find "$dir" -name '*.npz' 2>/dev/null | head -5 | tee -a "$log"
        found=1
    fi
    if find "$dir" -name 'truth*.json' 2>/dev/null | grep -q .; then
        echo "ABSENT-FILE FAIL: truth*.json files found under $dir" | tee -a "$log"
        find "$dir" -name 'truth*.json' 2>/dev/null | head -5 | tee -a "$log"
        found=1
    fi
    if [ "$found" -eq 0 ]; then
        echo "Absent-file audit: PASS" | tee -a "$log"
    fi
    return "$found"
}

# ─────────────────────────────────────────────────────────────────────────────
# check_clus_jsonnet — confirm the local clus.jsonnet override has bee_sink=null
# The file that matters is wcp-porting/sbnd/pgrapher/experiment/sbnd/clus.jsonnet
# (not the sbnd_xin or sbnd_abhat copies).
# ─────────────────────────────────────────────────────────────────────────────
check_clus_jsonnet() {
    local log="${1:-/dev/stderr}"
    local jsonnet="$NUGRAPH_BASE/wcp-porting/sbnd/pgrapher/experiment/sbnd/clus.jsonnet"
    if [ ! -f "$jsonnet" ]; then
        echo "PREFLIGHT FAIL: local clus.jsonnet not found: $jsonnet" | tee -a "$log"
        return 1
    fi
    if ! grep -q 'bee_sink=null' "$jsonnet"; then
        echo "PREFLIGHT FAIL: clus.jsonnet missing bee_sink=null (intermediate H5 may be enabled)" | tee -a "$log"
        echo "  file: $jsonnet" | tee -a "$log"
        return 1
    fi
    if grep -q 'cvmfs.sbnd.opensciencegrid' "$jsonnet"; then
        echo "PREFLIGHT FAIL: clus.jsonnet references cvmfs path" | tee -a "$log"
        return 1
    fi
    echo "clus.jsonnet gate: PASS (bee_sink=null, no cvmfs)" | tee -a "$log"
}

# ─────────────────────────────────────────────────────────────────────────────
# count_manifest_rows — print number of data rows (excluding header)
# ─────────────────────────────────────────────────────────────────────────────
count_manifest_rows() {
    local manifest="$1"
    tail -n +2 "$manifest" | grep -c . || true
}

# ─────────────────────────────────────────────────────────────────────────────
# wait_socket — wait up to TIMEOUT seconds for Unix socket file to appear
# ─────────────────────────────────────────────────────────────────────────────
wait_socket() {
    local sockpath="$1"
    local timeout="${2:-90}"
    local log="${3:-/dev/stderr}"
    local elapsed=0
    echo "Waiting for socket: $sockpath (timeout=${timeout}s)" | tee -a "$log"
    while [ ! -S "$sockpath" ] && [ "$elapsed" -lt "$timeout" ]; do
        sleep 2
        elapsed=$((elapsed + 2))
    done
    if [ ! -S "$sockpath" ]; then
        echo "TIMEOUT: socket did not appear after ${timeout}s" | tee -a "$log"
        return 1
    fi
    echo "Socket appeared after ${elapsed}s" | tee -a "$log"
}

# ─────────────────────────────────────────────────────────────────────────────
# run_apptainer — launch container with the mode-specific container script
# The container script path is passed via NUGRAPH_CONTAINER_SCRIPT env var.
# ─────────────────────────────────────────────────────────────────────────────
run_apptainer() {
    local log="${1:-/dev/stderr}"
    echo "Launching apptainer container..." | tee -a "$log"
    echo "  Container script: $NUGRAPH_CONTAINER_SCRIPT" | tee -a "$log"
    echo "  SIF: $NUGRAPH_SIF" | tee -a "$log"
    EVENTGRAPH_IPC_PATH="$NUGRAPH_SOCKPATH" \
    NUGRAPH_MANIFEST="$NUGRAPH_MANIFEST" \
    NUGRAPH_OUTDIR="$NUGRAPH_OUTDIR" \
    NUGRAPH_N_EVENTS="${NUGRAPH_N_EVENTS:-0}" \
    apptainer exec \
        --fakeroot \
        --bind /lus/eagle \
        --bind /lus/grand \
        --overlay "$NUGRAPH_LARSOFT_SQS":ro \
        --overlay "$NUGRAPH_SBND_DELTA_SQS":ro \
        "$NUGRAPH_SIF" \
        bash -lc "bash '$NUGRAPH_CONTAINER_SCRIPT'"
}

# ─────────────────────────────────────────────────────────────────────────────
# print_verdict — print final pass/fail verdict
# ─────────────────────────────────────────────────────────────────────────────
print_verdict() {
    local verdict="$1"
    local log="${2:-/dev/stdout}"
    echo "" | tee -a "$log"
    echo "============================================================" | tee -a "$log"
    echo "UNIFIED NUGRAPH PRODUCTION VERDICT: $verdict" | tee -a "$log"
    echo "Time: $(date)" | tee -a "$log"
    echo "============================================================" | tee -a "$log"
}
