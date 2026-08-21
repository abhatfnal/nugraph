#!/bin/bash
# Simulation container-side script for unified NuGraph production.
# Runs INSIDE the SLF7 squashfs container via apptainer exec.
#
# Frozen at: WCT bc7f4af9  larwirecell 9295e2a3
# NOTE: The Aug 13 engineering run had HEAD at 0869668/6ead889 but compiled from
# working-tree modifications that were later committed at bc7f4af9/9295e2a3.
# See SIM_SOURCE_STATE_INTEGRITY_AUDIT_2026-08-20.md.
# FCL: wcls-img-clus-matching-xin-noint.fcl  SHA 857af5c3...
#
# Steps:
#   [0]   Environment setup and gate check
#   [1]   SHA gate: WCT=0869668, larwirecell=6ead889
#   [1/4] WCT waf rebuild (TrackFitting lifetime fix: clear_segments in TrackFitting + TaggerCheckSTM)
#   [2/4] wcdoctest-clus *clear_segments* regression gate
#   [3/4] larwirecell incremental CMake rebuild
#   [4/4] ONE lar run — all N events, source files from manifest, single IPC connection
#
# Environment variables (set by run_nugraph_production.sh before apptainer exec):
#   EVENTGRAPH_IPC_PATH — Unix socket path
#   NUGRAPH_MANIFEST    — producer manifest CSV (source_index,input_file,nskip,run,subrun,event,input_sha256)
#   NUGRAPH_OUTDIR      — output directory (for logs, events subdir)
#   NUGRAPH_N_EVENTS    — expected total event count (informational)
set -uo pipefail

# NUGRAPH_WORKSPACE_DIR: root of the WCT/larwirecell compiled workspace.
# Must contain: wct-ap-yuhw/, larwirecell-dev/, opt/, mrb-dev/, wcp-porting/sbnd/
# Override by setting NUGRAPH_WORKSPACE_DIR before calling apptainer.
BASE="${NUGRAPH_WORKSPACE_DIR:-/lus/eagle/projects/neutrinoGPU/abhat/sbnd/sample_generation_port/work/haiwang-current}"
OPT=$BASE/opt
MRB_BUILD=$BASE/mrb-dev/build_slf7.x86_64
WCT_SRC=$BASE/wct-ap-yuhw
LWC_SRC=$BASE/larwirecell-dev

OUTDIR="${NUGRAPH_OUTDIR:-$BASE/unified-run}"
LOG=$OUTDIR/logs/container.log
STATUS=$OUTDIR/logs/lar_status.txt
MANIFEST="${NUGRAPH_MANIFEST}"

mkdir -p "$OUTDIR/logs" "$OUTDIR/events"

echo "=== UNIFIED NUGRAPH PRODUCTION: sim container ===" | tee "$LOG"
echo "Time: $(date)"                                      | tee -a "$LOG"
echo "Host: $(hostname)"                                  | tee -a "$LOG"
echo "EVENTGRAPH_IPC_PATH: ${EVENTGRAPH_IPC_PATH:-<NOT SET>}" | tee -a "$LOG"
echo "NUGRAPH_MANIFEST: $MANIFEST"                        | tee -a "$LOG"
echo "NUGRAPH_N_EVENTS: ${NUGRAPH_N_EVENTS:-?}"          | tee -a "$LOG"

if [ -z "${EVENTGRAPH_IPC_PATH:-}" ]; then
    echo "ERROR: EVENTGRAPH_IPC_PATH is not set" | tee -a "$LOG"; exit 1
fi

# ============================================================
# [0] Environment setup
# ============================================================
source /lus/eagle/projects/neutrinoGPU/larsoft_hpc/envs/sbndcode-v10_14_02_04.env 2>/dev/null

GCC_DIR=/lus/flare/projects/neutrinoGPU/scisoft/larsoft/gcc/v12_1_0/Linux64bit+3.10-2.17/bin
export CC=$GCC_DIR/gcc CXX=$GCC_DIR/g++ PATH=$GCC_DIR:$PATH
export PKG_CONFIG_PATH=$OPT/lib/pkgconfig:${PKG_CONFIG_PATH:-}

CUSTOM_LARWIRECELL_LIB=$OPT/larwirecell/v10_01_28/slf7.x86_64.e26.prof/lib

# ============================================================
# [1] SHA gate: WCT and larwirecell
# ============================================================
WCT_COMMIT=$(cd "$WCT_SRC" && git rev-parse HEAD)
echo "WCT commit: $WCT_COMMIT" | tee -a "$LOG"
if [[ "$WCT_COMMIT" != bc7f4af9* ]]; then
    echo "ERROR: WCT not at frozen bc7f4af9 (got $WCT_COMMIT)" | tee -a "$LOG"; exit 1
fi
echo "WCT SHA gate: PASS" | tee -a "$LOG"

LWC_COMMIT=$(cd "$LWC_SRC" && git rev-parse HEAD)
echo "larwirecell commit: $LWC_COMMIT" | tee -a "$LOG"
if [[ "$LWC_COMMIT" != 9295e2a3* ]]; then
    echo "ERROR: larwirecell not at frozen 9295e2a3 (got $LWC_COMMIT)" | tee -a "$LOG"; exit 1
fi
echo "larwirecell SHA gate: PASS" | tee -a "$LOG"

# ============================================================
# [1/4] Rebuild WCT (waf) — three-part clear_segments() lifetime fix
# ============================================================
echo "" | tee -a "$LOG"
echo "=== [1/4] WCT waf rebuild (TrackFitting lifetime fix) ===" | tee -a "$LOG"
echo "Time: $(date)" | tee -a "$LOG"
sha256sum \
    "$WCT_SRC/clus/src/TrackFitting.cxx" \
    "$WCT_SRC/clus/src/TaggerCheckSTM.cxx" \
    "$WCT_SRC/clus/test/doctest_trackfitting_clear_segments.cxx" \
    2>/dev/null | tee -a "$LOG"

cd "$WCT_SRC"
python3 "$WCT_SRC/wcb" --notests install -j8 > "$OUTDIR/logs/wct_rebuild.log" 2>&1
WCT_BUILD_EXIT=$?
echo "WCT build exit: $WCT_BUILD_EXIT" | tee -a "$LOG"
if [ $WCT_BUILD_EXIT -ne 0 ]; then
    echo "WCT BUILD FAILED -- last 40 lines:" | tee -a "$LOG"
    tail -40 "$OUTDIR/logs/wct_rebuild.log" | tee -a "$LOG"; exit 1
fi
echo "WCT build: PASS" | tee -a "$LOG"
stat -c '%y  %n' "$OPT/lib/libWireCellClus.so" | tee -a "$LOG"

# ============================================================
# [2/4] wcdoctest-clus regression gate
# ============================================================
echo "" | tee -a "$LOG"
echo "=== [2/4] wcdoctest-clus (*clear_segments*) ===" | tee -a "$LOG"
echo "Time: $(date)" | tee -a "$LOG"

CLUS_DOCTEST=$WCT_SRC/build/clus/wcdoctest-clus
export LD_LIBRARY_PATH=$OPT/lib:${LD_LIBRARY_PATH:-}

"$CLUS_DOCTEST" -tc="*clear_segments*" > "$OUTDIR/logs/doctest_output.log" 2>&1
DOCTEST_EXIT=$?
echo "doctest exit: $DOCTEST_EXIT" | tee -a "$LOG"
cat "$OUTDIR/logs/doctest_output.log" | tee -a "$LOG"
if [ $DOCTEST_EXIT -ne 0 ]; then
    echo "DOCTEST FAILED — aborting before lar" | tee -a "$LOG"; exit 1
fi
echo "wcdoctest-clus: PASS" | tee -a "$LOG"

# ============================================================
# [3/4] larwirecell incremental CMake rebuild
# ============================================================
echo "" | tee -a "$LOG"
echo "=== [3/4] larwirecell incremental build ===" | tee -a "$LOG"
echo "Time: $(date)" | tee -a "$LOG"

LARSOFT_CMAKE_BASE=/lus/flare/projects/neutrinoGPU/scisoft/larsoft/cmake
CMAKE=""
for VER in v3_27_4 v3_26_4 v3_25_2 v3_24_1 v3_22_2; do
    CAND="$LARSOFT_CMAKE_BASE/$VER/Linux64bit+3.10-2.17/bin/cmake"
    if [ -x "$CAND" ]; then CMAKE="$CAND"; echo "Using cmake $VER" | tee -a "$LOG"; break; fi
done
[ -z "$CMAKE" ] && { echo "cmake not found" | tee -a "$LOG"; exit 1; }

touch "$LWC_SRC/larwirecell/aiml/EventGraphIPC.cxx"
touch "$LWC_SRC/larwirecell/aiml/EventGraphIPC.h"
touch "$LWC_SRC/larwirecell/aiml/TensorSetLabeler.cxx"
touch "$LWC_SRC/larwirecell/aiml/TensorSetLabeler.h"
"$CMAKE" --build "$MRB_BUILD" -j8 > "$OUTDIR/logs/build_lwc.log" 2>&1
LWC_BUILD_EXIT=$?
echo "larwirecell build exit: $LWC_BUILD_EXIT" | tee -a "$LOG"
if [ $LWC_BUILD_EXIT -ne 0 ]; then
    echo "BUILD FAILED -- last 30 lines:" | tee -a "$LOG"
    tail -30 "$OUTDIR/logs/build_lwc.log" | tee -a "$LOG"; exit 1
fi

mkdir -p "$CUSTOM_LARWIRECELL_LIB"
while IFS= read -r lib; do
    cp "$lib" "$CUSTOM_LARWIRECELL_LIB/" \
        || { echo "  COPY FAILED: $lib" | tee -a "$LOG"; exit 1; }
    echo "  Installed: $(basename "$lib")" | tee -a "$LOG"
done < <(find "$MRB_BUILD" -name 'libWireCell*.so' 2>/dev/null)
stat -c '%y  %n' "$CUSTOM_LARWIRECELL_LIB/libWireCellAIML.so" 2>/dev/null | tee -a "$LOG"

UPS_WIRECELL_LIB=$WIRECELL_FQ_DIR/lib
UPS_LARWIRECELL_LIB=$LARWIRECELL_FQ_DIR/lib
export LD_LIBRARY_PATH=$CUSTOM_LARWIRECELL_LIB:$OPT/lib:$UPS_WIRECELL_LIB:$UPS_LARWIRECELL_LIB:${LD_LIBRARY_PATH:-}
export CET_PLUGIN_PATH=$CUSTOM_LARWIRECELL_LIB:$OPT/lib:$UPS_WIRECELL_LIB:$UPS_LARWIRECELL_LIB:${CET_PLUGIN_PATH:-}

CUSTOM_LWC_SO="$CUSTOM_LARWIRECELL_LIB/libWireCellLarsoft.so"
[ ! -f "$CUSTOM_LWC_SO" ] && { echo "PREFLIGHT FAIL: $CUSTOM_LWC_SO not found" | tee -a "$LOG"; exit 1; }
REAL_LWC_SO=$(realpath "$CUSTOM_LWC_SO")
if [[ "$REAL_LWC_SO" == /lus/flare/* ]]; then
    echo "PREFLIGHT FAIL: resolves to /lus/flare (read-only UPS)" | tee -a "$LOG"; exit 1
fi
echo "Library provenance: PASS ($REAL_LWC_SO)" | tee -a "$LOG"

# ============================================================
# WIRECELL_PATH and FHICL_FILE_PATH
# ============================================================
WCD_BASE=/lus/eagle/projects/neutrinoGPU/snehadri/wct/spack/opt/spack/linux-x86_64_v3/wire-cell-data-0.2.0-jbu22fdchzcf5ii5nvepy6fcgpsf4cnu/share/wirecell
WCP_SBND=$BASE/wcp-porting/sbnd
WCT_CFG=$WCT_SRC/cfg
SBND_XIN=$WCP_SBND/sbnd_xin
PHOTODET=$WCD_BASE/sbnd/photodet
WCD_SHARE=$WCD_BASE
LARWIRECELL_FCL=$OPT/larwirecell/v10_01_28/slf7.x86_64.e26.prof/fcl

export WIRECELL_PATH="$WCP_SBND:$WCT_CFG:$SBND_XIN:$PHOTODET:$WCD_SHARE:${WIRECELL_PATH:-}"
export FHICL_FILE_PATH="$WCP_SBND:$LARWIRECELL_FCL:${FHICL_FILE_PATH:-}"

LAR=$ART_FQ_DIR/bin/lar

# ============================================================
# [4/4] ONE lar run — all events in a single IPC session
# Parse unique source files from manifest (in order of first appearance)
# ============================================================
echo "" | tee -a "$LOG"
echo "=== [4/4] lar run (single IPC session, all events) ===" | tee -a "$LOG"
echo "Time: $(date)" | tee -a "$LOG"

if [ ! -f "$MANIFEST" ]; then
    echo "ERROR: manifest not found: $MANIFEST" | tee -a "$LOG"; exit 1
fi
N_ROWS=$(tail -n +2 "$MANIFEST" | grep -c .) || true
N_EVENTS="${NUGRAPH_N_EVENTS:-$N_ROWS}"
echo "Manifest rows: $N_ROWS  Expected events: $N_EVENTS" | tee -a "$LOG"

# Build unique ordered list of input files from manifest column 2 (0-indexed)
mapfile -t UNIQUE_FILES < <(tail -n +2 "$MANIFEST" | awk -F, '{print $2}' | awk '!seen[$0]++')
echo "Source files (${#UNIQUE_FILES[@]} unique):" | tee -a "$LOG"
SOURCE_ARGS=()
for f in "${UNIQUE_FILES[@]}"; do
    echo "  $f" | tee -a "$LOG"
    [ ! -f "$f" ] && { echo "ERROR: source file not found: $f" | tee -a "$LOG"; exit 1; }
    SOURCE_ARGS+=("-s" "$f")
done

echo "FCL: wcls-img-clus-matching-xin-noint.fcl" | tee -a "$LOG"
echo "EVENTGRAPH_IPC_PATH: $EVENTGRAPH_IPC_PATH" | tee -a "$LOG"

KDIR="$OUTDIR/events/run_all"
mkdir -p "$KDIR"
printf "%-15s %-9s %-9s %s\n" "run_tag" "exit_code" "wall_sec" "notes" > "$STATUS"

START_EPOCH=$(date +%s)
(
    cd "$KDIR"
    /usr/bin/time -v "$LAR" \
        --nskip 0 \
        -n "$N_EVENTS" \
        -c wcls-img-clus-matching-xin-noint.fcl \
        --no-output \
        "${SOURCE_ARGS[@]}"
) > "$KDIR/lar_run.log" 2>&1
LAR_EXIT=$?
END_EPOCH=$(date +%s)
WALL_SEC=$((END_EPOCH - START_EPOCH))
PEAK_RSS=$(grep -i "Maximum resident" "$KDIR/lar_run.log" 2>/dev/null | awk '{print $NF}' | head -1)
[ -z "$PEAK_RSS" ] && PEAK_RSS="?"

echo "  exit=$LAR_EXIT  wall=${WALL_SEC}s  peak_rss=${PEAK_RSS}kB" | tee -a "$LOG"

NOTES="OK"
[ $LAR_EXIT -ne 0 ] && NOTES="LAR_FAIL"
printf "%-15s %-9d %-9d %s\n" "all_events" "$LAR_EXIT" "$WALL_SEC" "$NOTES" >> "$STATUS"

if [ $LAR_EXIT -ne 0 ]; then
    echo "NUGRAPH SIM RUN: LAR FAIL (exit=$LAR_EXIT)" | tee -a "$LOG"
    echo "--- last 60 lines of lar_run.log ---" | tee -a "$LOG"
    tail -60 "$KDIR/lar_run.log" | tee -a "$LOG"
    exit 1
fi

for pattern in "SIGSEGV" "Segmentation fault" "signal 11" "double free" "invalid pointer"; do
    if grep -qi "$pattern" "$KDIR/lar_run.log" 2>/dev/null; then
        echo "WARNING: crash indicator found in lar log: $pattern" | tee -a "$LOG"
    fi
done

echo "" | tee -a "$LOG"
echo "=== sim container: PASS ===" | tee -a "$LOG"
echo "Time: $(date)" | tee -a "$LOG"
exit 0
