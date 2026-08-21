#!/bin/bash
# Real-data container-side script for unified NuGraph production.
# Runs INSIDE the SLF7 squashfs container via apptainer exec.
#
# Frozen at: WCT bc7f4af9  larwirecell 9295e2a3
# FCL: wcls-img-clus-matching-xin-data-noint.fcl  SHA 0650836f...
#
# Steps:
#   [0]   Environment setup
#   [1]   SHA gate: WCT=bc7f4af9, larwirecell=9295e2a3
#   [2]   larwirecell incremental CMake rebuild
#   [3]   WIRECELL_PATH and FHICL_FILE_PATH
#   [4]   Manifest check
#   [4b]  BNBSpillInfo ClassVersion 15->16 patch (identical to Case A validated patch)
#   [5]   N sequential lar runs — one per manifest row, --nskip N -n 1
#
# Environment variables (set by run_nugraph_production.sh before apptainer exec):
#   EVENTGRAPH_IPC_PATH — Unix socket path
#   NUGRAPH_MANIFEST    — producer manifest CSV (source_index,input_file,nskip,run,subrun,event,input_sha256)
#   NUGRAPH_OUTDIR      — output directory (for logs, runtime subdir)
set -uo pipefail

# NUGRAPH_WORKSPACE_DIR: root of the WCT/larwirecell compiled workspace.
# Must contain: wct-ap-yuhw/, larwirecell-dev/, opt/, mrb-dev/, wcp-porting/sbnd/
# Override by setting NUGRAPH_WORKSPACE_DIR before calling apptainer.
BASE="${NUGRAPH_WORKSPACE_DIR:-/lus/eagle/projects/neutrinoGPU/abhat/sbnd/sample_generation_port/work/haiwang-current}"
OPT=$BASE/opt
MRB_BUILD=$BASE/mrb-dev/build_slf7.x86_64
WCT_SRC=$BASE/wct-ap-yuhw
LWC_SRC=$BASE/larwirecell-dev

# NUGRAPH_DATA_FCL_DIR: directory containing wcls-img-clus-matching-xin-data-noint.fcl
# Default: canonical location in the validated NC-sideband pipeline (shared Eagle)
# Override by setting NUGRAPH_DATA_FCL_DIR (e.g., to the configs/fcl/ dir in the NuGraph repo clone).
FCL_DIR="${NUGRAPH_DATA_FCL_DIR:-/lus/eagle/projects/neutrinoGPU/abhat/sbnd/clustering/engineering-nc-sideband-19evt-new-pipeline/scripts/19event_run_v1}"

OUTDIR="${NUGRAPH_OUTDIR:-$BASE/unified-run}"
LOG=$OUTDIR/logs/container.log
STATUS=$OUTDIR/logs/lar_status.txt
MANIFEST="${NUGRAPH_MANIFEST}"

mkdir -p "$OUTDIR/logs" "$OUTDIR/runtime"

echo "=== UNIFIED NUGRAPH PRODUCTION: data container ===" | tee "$LOG"
echo "Time: $(date)"                                       | tee -a "$LOG"
echo "Host: $(hostname)"                                   | tee -a "$LOG"
echo "EVENTGRAPH_IPC_PATH: ${EVENTGRAPH_IPC_PATH:-<NOT SET>}" | tee -a "$LOG"
echo "NUGRAPH_MANIFEST: $MANIFEST"                         | tee -a "$LOG"

if [ -z "${EVENTGRAPH_IPC_PATH:-}" ]; then
    echo "ERROR: EVENTGRAPH_IPC_PATH not set" | tee -a "$LOG"; exit 1
fi

# ============================================================
# [0] Environment setup
# ============================================================
source /lus/eagle/projects/neutrinoGPU/larsoft_hpc/envs/sbndcode-v10_14_02_04.env 2>/dev/null

CUSTOM_LARWIRECELL_LIB=$OPT/larwirecell/v10_01_28/slf7.x86_64.e26.prof/lib

GCC_DIR=/lus/flare/projects/neutrinoGPU/scisoft/larsoft/gcc/v12_1_0/Linux64bit+3.10-2.17/bin
export CC=$GCC_DIR/gcc CXX=$GCC_DIR/g++ PATH=$GCC_DIR:$PATH
export PKG_CONFIG_PATH=$OPT/lib/pkgconfig:${PKG_CONFIG_PATH:-}
export LD_LIBRARY_PATH=$CUSTOM_LARWIRECELL_LIB:$OPT/lib:${LD_LIBRARY_PATH:-}

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
# [2] larwirecell incremental CMake rebuild
# ============================================================
echo "" | tee -a "$LOG"
echo "=== [2] larwirecell incremental build ===" | tee -a "$LOG"
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
BUILD_EXIT=$?
echo "larwirecell build exit: $BUILD_EXIT" | tee -a "$LOG"
if [ $BUILD_EXIT -ne 0 ]; then
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
# [3] WireCell and FHICL paths
# ============================================================
WCD_BASE=/lus/eagle/projects/neutrinoGPU/snehadri/wct/spack/opt/spack/linux-x86_64_v3/wire-cell-data-0.2.0-jbu22fdchzcf5ii5nvepy6fcgpsf4cnu/share/wirecell
WCP_SBND=$BASE/wcp-porting/sbnd
WCT_CFG=$WCT_SRC/cfg
SBND_XIN=$WCP_SBND/sbnd_xin
PHOTODET=$WCD_BASE/sbnd/photodet
WCD_SHARE=$WCD_BASE
LARWIRECELL_FCL=$OPT/larwirecell/v10_01_28/slf7.x86_64.e26.prof/fcl

export WIRECELL_PATH="$WCP_SBND:$WCT_CFG:$SBND_XIN:$PHOTODET:$WCD_SHARE:${WIRECELL_PATH:-}"
export FHICL_FILE_PATH="$FCL_DIR:$WCP_SBND:$LARWIRECELL_FCL:${FHICL_FILE_PATH:-}"

LAR=$ART_FQ_DIR/bin/lar

# ============================================================
# [4] Manifest check
# ============================================================
if [ ! -f "$MANIFEST" ]; then
    echo "ERROR: manifest not found: $MANIFEST" | tee -a "$LOG"; exit 1
fi
N_ROWS=$(tail -n +2 "$MANIFEST" | grep -c .) || true
echo "Manifest rows: $N_ROWS" | tee -a "$LOG"
[ "$N_ROWS" -lt 1 ] && { echo "ERROR: manifest is empty" | tee -a "$LOG"; exit 1; }

# ============================================================
# [4b] sbnobj BNBSpillInfo patch: bump ClassVersion 15->16
# Uses first data file from manifest. Identical to Case A validated patch.
# ============================================================
echo "" | tee -a "$LOG"
echo "=== [4b] BNBSpillInfo patch (v15->v16) ===" | tee -a "$LOG"
echo "Time: $(date)" | tee -a "$LOG"

PATCH_DIR=$OUTDIR/runtime/sbnobj_patch
mkdir -p "$PATCH_DIR"

DATA_FILE=$(awk -F, 'NR==2{print $2}' "$MANIFEST")
SBNOBJ_V04_SRC=/lus/flare/projects/neutrinoGPU/scisoft/larsoft/sbnobj/v10_14_02_04/source/sbnobj/Common/POTAccounting
SBNOBJ_V04_INC=/lus/flare/projects/neutrinoGPU/scisoft/larsoft/sbnobj/v10_14_02_04/include
CURRENT_CS=28411542

cat > "$PATCH_DIR/get_cs.C" << ROOTEOF
{
    TFile *f = TFile::Open("$DATA_FILE", "READ");
    if (!f || f->IsZombie()) { printf("CS_ERROR\n"); return; }
    TList *sil = f->GetStreamerInfoList();
    if (!sil) { printf("CS_NOLIST\n"); return; }
    TIter next(sil);
    TObject *o;
    while ((o = next())) {
        TStreamerInfo *si = dynamic_cast<TStreamerInfo*>(o);
        if (!si) continue;
        if (strcmp(si->GetName(), "sbn::BNBSpillInfo") == 0) {
            printf("BNBCS %d %u\n", si->GetClassVersion(), si->GetCheckSum());
        }
    }
    f->Close();
}
ROOTEOF

LD_NOSBNOBJ=$(echo "$LD_LIBRARY_PATH" | tr ':' '\n' | grep -v '/sbnobj/' | tr '\n' ':')
CS_RAW=$(LD_LIBRARY_PATH="$LD_NOSBNOBJ" \
    "$ROOTSYS/bin/root" -l -b -q "$PATCH_DIR/get_cs.C" 2>/dev/null)
OLD_CS=$(echo "$CS_RAW" | awk '/^BNBCS 15 /{print $3}')

echo "$CS_RAW" | grep "^BNBCS" | tee -a "$LOG"
echo "In-memory BNBSpillInfo: version=15 checksum=$CURRENT_CS" | tee -a "$LOG"

if [ -z "$OLD_CS" ]; then
    echo "No ClassVersion=15 entry -- skipping patch" | tee -a "$LOG"
elif [ "$OLD_CS" = "$CURRENT_CS" ]; then
    echo "Checksums match -- skipping patch" | tee -a "$LOG"
else
    echo "Mismatch: data=$OLD_CS vs memory=$CURRENT_CS -- applying patch" | tee -a "$LOG"

    cat > "$PATCH_DIR/patch_classes_def.py" << 'PYEOF'
import sys
in_f, out_f, old_cs, new_cs = sys.argv[1:]
with open(in_f) as f:
    xml = f.read()
xml = xml.replace(
    'class name="sbn::BNBSpillInfo" ClassVersion="15">',
    'class name="sbn::BNBSpillInfo" ClassVersion="16">'
)
old_entry = f'   <version ClassVersion="15" checksum="{new_cs}"/>'
new_entries = (
    f'   <version ClassVersion="16" checksum="{new_cs}"/>\n'
    f'   <version ClassVersion="15" checksum="{old_cs}"/>'
)
xml = xml.replace(old_entry, new_entries)
with open(out_f, 'w') as f:
    f.write(xml)
print(f"classes_def.xml patched: BNBSpillInfo ClassVersion 15->16, old_cs={old_cs}")
PYEOF

    cp "$SBNOBJ_V04_SRC/classes.h" "$PATCH_DIR/"
    python3 "$PATCH_DIR/patch_classes_def.py" \
        "$SBNOBJ_V04_SRC/classes_def.xml" \
        "$PATCH_DIR/classes_def.xml" \
        "$OLD_CS" "$CURRENT_CS" | tee -a "$LOG"

    grep -A7 'BNBSpillInfo.*ClassVersion' "$PATCH_DIR/classes_def.xml" | tee -a "$LOG"

    cd "$PATCH_DIR"
    ROOT_INC_FLAGS=$(echo "$ROOT_INCLUDE_PATH" | tr ':' '\n' | grep -v '^$' | \
                    sed 's|^|-I|' | tr '\n' ' ')

    "$ROOTSYS/bin/rootcling" -f POTAccounting_dict.cxx \
        -s libsbnobj_Common_POTAccounting_dict \
        -rmf libsbnobj_Common_POTAccounting_dict.rootmap \
        -rml libsbnobj_Common_POTAccounting_dict.so \
        "-I$SBNOBJ_V04_INC" $ROOT_INC_FLAGS \
        classes.h classes_def.xml >> "$LOG" 2>&1
    RCLING_EXIT=$?
    echo "rootcling exit: $RCLING_EXIT" | tee -a "$LOG"
    [ $RCLING_EXIT -ne 0 ] && { echo "ERROR: rootcling failed" | tee -a "$LOG"; exit 1; }

    $CXX -shared -fPIC -std=c++17 -O2 \
        -o "$PATCH_DIR/libsbnobj_Common_POTAccounting_dict.so" \
        "$PATCH_DIR/POTAccounting_dict.cxx" \
        "-I$SBNOBJ_V04_INC" "-I$ROOTSYS/include" $ROOT_INC_FLAGS \
        "-L$ROOTSYS/lib" -lCore "-Wl,-rpath,$ROOTSYS/lib" >> "$LOG" 2>&1
    COMPILE_EXIT=$?
    echo "dict compile exit: $COMPILE_EXIT" | tee -a "$LOG"
    [ $COMPILE_EXIT -ne 0 ] && { echo "ERROR: dict compile failed" | tee -a "$LOG"; exit 1; }

    export LD_LIBRARY_PATH="$PATCH_DIR:$LD_LIBRARY_PATH"
    export CET_PLUGIN_PATH="$PATCH_DIR:$CET_PLUGIN_PATH"
    echo "Patched dict injected: $PATCH_DIR" | tee -a "$LOG"
    ls -lh "$PATCH_DIR/libsbnobj_Common_POTAccounting_dict.so" | tee -a "$LOG"
fi

# ============================================================
# [5] N sequential lar runs — one per manifest row
# ============================================================
echo "" | tee -a "$LOG"
echo "=== [5] Sequential lar runs (one per manifest row) ===" | tee -a "$LOG"
echo "Time: $(date)" | tee -a "$LOG"
echo "FCL: wcls-img-clus-matching-xin-data-noint.fcl" | tee -a "$LOG"
echo "FCL_DIR: $FCL_DIR" | tee -a "$LOG"

printf "%-6s %-9s %-9s %s\n" "sidx" "exit_code" "wall_sec" "notes" > "$STATUS"

LAR_FAIL_COUNT=0
while IFS=, read -r SOURCE_INDEX INPUT_FILE NSKIP RUN SUBRUN EVENT INPUT_SHA256; do
    INPUT_SHA256="${INPUT_SHA256//$'\r'/}"
    [ "$SOURCE_INDEX" = "source_index" ] && continue

    KDIR=$OUTDIR/runtime/event_${SOURCE_INDEX}
    mkdir -p "$KDIR"

    echo "--- sidx=$SOURCE_INDEX  R/SR/E=$RUN/$SUBRUN/$EVENT  nskip=$NSKIP ---" | tee -a "$LOG"
    echo "  input: $(basename "$INPUT_FILE")" | tee -a "$LOG"
    echo "Time: $(date)" | tee -a "$LOG"

    START_EPOCH=$(date +%s)
    (
        cd "$KDIR"
        /usr/bin/time -v "$LAR" --nskip "$NSKIP" -n 1 \
            -c wcls-img-clus-matching-xin-data-noint.fcl \
            --no-output \
            -s "$INPUT_FILE"
    ) > "$KDIR/lar_run.log" 2>&1
    LAR_EXIT=$?
    END_EPOCH=$(date +%s)
    WALL_SEC=$((END_EPOCH - START_EPOCH))
    PEAK_RSS=$(grep -i "Maximum resident" "$KDIR/lar_run.log" 2>/dev/null | awk '{print $NF}' | head -1)
    [ -z "$PEAK_RSS" ] && PEAK_RSS="?"

    echo "  exit=$LAR_EXIT  wall=${WALL_SEC}s  peak_rss=${PEAK_RSS}kB" | tee -a "$LOG"

    NOTES="OK"; [ $LAR_EXIT -ne 0 ] && NOTES="LAR_FAIL"
    printf "%-6d %-9d %-9d %s\n" "$SOURCE_INDEX" "$LAR_EXIT" "$WALL_SEC" "$NOTES" >> "$STATUS"

    if [ $LAR_EXIT -ne 0 ]; then
        echo "  LAR FAIL at sidx=$SOURCE_INDEX R/SR/E=$RUN/$SUBRUN/$EVENT -- continuing" | tee -a "$LOG"
        tail -60 "$KDIR/lar_run.log" | tee -a "$LOG"
        LAR_FAIL_COUNT=$((LAR_FAIL_COUNT + 1))
        continue
    fi
    echo "  sidx=$SOURCE_INDEX: LAR_PASS" | tee -a "$LOG"
done < "$MANIFEST"

echo "" | tee -a "$LOG"
N_PASS=$((N_ROWS - LAR_FAIL_COUNT))
echo "=== lar loop complete: $LAR_FAIL_COUNT failed, $N_PASS passed ===" | tee -a "$LOG"
echo "Time: $(date)" | tee -a "$LOG"
exit 0
