#!/bin/bash
# Unified NuGraph production driver.
# Supports --mode sim (MC simulation) and --mode data (real SBND data).
#
# Usage:
#   run_nugraph_production.sh --mode sim  \
#       --manifest source_events.csv       \
#       --output-h5 out.h5                 \
#       --output-dir /path/to/run/dir      \
#       [--receiver-manifest recv.csv]     \
#       [--report receiver_report.json]    \
#       [--dry-run]
#
#   run_nugraph_production.sh --mode data \
#       --manifest nc_sideband_19evt.csv   \
#       --receiver-manifest recv_17evt.csv \
#       --output-h5 out.h5                 \
#       --output-dir /path/to/run/dir      \
#       [--report receiver_report.json]    \
#       [--dry-run]
#
# Frozen SHA values and full audit documented in:
#   reports/UNIFIED_PIPELINE_EXISTING_WORKFLOW_AUDIT_2026-08-20.md
set -uo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Locate driver directory and source common functions
# ─────────────────────────────────────────────────────────────────────────────
DRIVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$DRIVER_DIR/lib/common.sh"

# ─────────────────────────────────────────────────────────────────────────────
# Argument parsing
# ─────────────────────────────────────────────────────────────────────────────
MODE=""
MANIFEST=""
RECEIVER_MANIFEST=""
OUTPUT_H5=""
OUTPUT_DIR=""
REPORT=""
DRY_RUN=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode)             MODE="$2";              shift 2 ;;
        --manifest)         MANIFEST="$2";          shift 2 ;;
        --receiver-manifest) RECEIVER_MANIFEST="$2"; shift 2 ;;
        --output-h5)        OUTPUT_H5="$2";         shift 2 ;;
        --output-dir)       OUTPUT_DIR="$2";        shift 2 ;;
        --report)           REPORT="$2";            shift 2 ;;
        --dry-run)          DRY_RUN=1;              shift   ;;
        -h|--help)
            grep '^#' "$0" | head -25 | sed 's/^# *//'
            exit 0 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

# ─────────────────────────────────────────────────────────────────────────────
# Validate required arguments
# ─────────────────────────────────────────────────────────────────────────────
if [ -z "$MODE" ]; then
    echo "ERROR: --mode sim|data is required"; exit 1
fi
if [[ "$MODE" != "sim" && "$MODE" != "data" ]]; then
    echo "ERROR: --mode must be 'sim' or 'data' (got '$MODE')"; exit 1
fi
if [ -z "$MANIFEST" ]; then
    echo "ERROR: --manifest is required"; exit 1
fi
if [ -z "$OUTPUT_H5" ]; then
    echo "ERROR: --output-h5 is required"; exit 1
fi
if [ -z "$OUTPUT_DIR" ]; then
    echo "ERROR: --output-dir is required"; exit 1
fi

# Default receiver manifest to producer manifest if not specified
[ -z "$RECEIVER_MANIFEST" ] && RECEIVER_MANIFEST="$MANIFEST"

# Default report path
[ -z "$REPORT" ] && REPORT="$OUTPUT_DIR/logs/receiver_report.json"

# ─────────────────────────────────────────────────────────────────────────────
# Source mode-specific config
# ─────────────────────────────────────────────────────────────────────────────
source "$DRIVER_DIR/configs/${MODE}_defaults.sh"

NUGRAPH_CONTAINER_SCRIPT="$DRIVER_DIR/lib/containers/run_${MODE}_container.sh"
export NUGRAPH_OUTDIR="$OUTPUT_DIR"
export NUGRAPH_MANIFEST="$MANIFEST"

mkdir -p "$OUTPUT_DIR/logs" "$OUTPUT_DIR/canonical"

LOG="$OUTPUT_DIR/logs/run_nugraph_production.log"

echo "=== UNIFIED NUGRAPH PRODUCTION ===" | tee "$LOG"
echo "Date: $(date)" | tee -a "$LOG"
echo "Mode: $MODE" | tee -a "$LOG"
echo "Manifest: $MANIFEST" | tee -a "$LOG"
echo "Receiver manifest: $RECEIVER_MANIFEST" | tee -a "$LOG"
echo "Output H5: $OUTPUT_H5" | tee -a "$LOG"
echo "Output dir: $OUTPUT_DIR" | tee -a "$LOG"
echo "Dry run: $DRY_RUN" | tee -a "$LOG"
echo "" | tee -a "$LOG"

# ─────────────────────────────────────────────────────────────────────────────
# PREFLIGHT CHECKS
# ─────────────────────────────────────────────────────────────────────────────
echo "=== PREFLIGHT ===" | tee -a "$LOG"

PREFLIGHT_FAIL=0

# 1. Manifest exists and has rows
if [ ! -f "$MANIFEST" ]; then
    echo "PREFLIGHT FAIL: manifest not found: $MANIFEST" | tee -a "$LOG"; PREFLIGHT_FAIL=1
else
    N_PROD_ROWS=$(count_manifest_rows "$MANIFEST")
    echo "Producer manifest: $N_PROD_ROWS rows" | tee -a "$LOG"
    [ "$N_PROD_ROWS" -lt 1 ] && { echo "PREFLIGHT FAIL: empty manifest" | tee -a "$LOG"; PREFLIGHT_FAIL=1; }
fi

# 2. Receiver manifest
if [ ! -f "$RECEIVER_MANIFEST" ]; then
    echo "PREFLIGHT FAIL: receiver manifest not found: $RECEIVER_MANIFEST" | tee -a "$LOG"; PREFLIGHT_FAIL=1
else
    N_RECV_ROWS=$(count_manifest_rows "$RECEIVER_MANIFEST")
    echo "Receiver manifest: $N_RECV_ROWS rows" | tee -a "$LOG"
fi

# 3. Output H5 collision
check_output_no_collision "$OUTPUT_H5" "$LOG" || PREFLIGHT_FAIL=1

# 4. .partial gate
check_no_partial "$OUTPUT_H5" "$LOG" || PREFLIGHT_FAIL=1

# 5. Receiver SHA gate
check_receiver_sha "$LOG" || PREFLIGHT_FAIL=1

# 6. clus.jsonnet check
check_clus_jsonnet "$LOG" || PREFLIGHT_FAIL=1

# 7. Pre-flight absent-file check (output dir)
check_absent_files "$OUTPUT_DIR" "$LOG" || PREFLIGHT_FAIL=1

# 8. Container script exists
if [ ! -f "$NUGRAPH_CONTAINER_SCRIPT" ]; then
    echo "PREFLIGHT FAIL: container script not found: $NUGRAPH_CONTAINER_SCRIPT" | tee -a "$LOG"
    PREFLIGHT_FAIL=1
else
    echo "Container script: FOUND ($NUGRAPH_CONTAINER_SCRIPT)" | tee -a "$LOG"
fi

# 9. Mode-specific: FCL SHA gate
FCL_PATH="${NUGRAPH_FCL_DIR:-$NUGRAPH_BASE/wcp-porting/sbnd}/$NUGRAPH_FCL_NAME"
if [ ! -f "$FCL_PATH" ]; then
    echo "PREFLIGHT FAIL: FCL not found: $FCL_PATH" | tee -a "$LOG"; PREFLIGHT_FAIL=1
else
    FCL_ACTUAL=$(sha256sum "$FCL_PATH" | awk '{print $1}')
    echo "FCL SHA256: $FCL_ACTUAL" | tee -a "$LOG"
    if [[ "$FCL_ACTUAL" != ${NUGRAPH_FCL_SHA}* && "$FCL_ACTUAL" != "$NUGRAPH_FCL_SHA" ]]; then
        echo "PREFLIGHT FAIL: FCL SHA mismatch for $NUGRAPH_FCL_NAME" | tee -a "$LOG"
        echo "  expected: $NUGRAPH_FCL_SHA" | tee -a "$LOG"
        echo "  got:      $FCL_ACTUAL" | tee -a "$LOG"
        PREFLIGHT_FAIL=1
    else
        echo "FCL SHA gate: PASS ($NUGRAPH_FCL_NAME)" | tee -a "$LOG"
    fi
fi

# 10. Input file SHAs from manifest
echo "Verifying input file SHAs from manifest..." | tee -a "$LOG"
SHA_FAIL=0
while IFS=, read -r SOURCE_INDEX INPUT_FILE NSKIP RUN SUBRUN EVENT INPUT_SHA256; do
    INPUT_SHA256="${INPUT_SHA256//$'\r'/}"
    [ "$SOURCE_INDEX" = "source_index" ] && continue
    [ -z "$INPUT_SHA256" ] && continue
    if [ ! -f "$INPUT_FILE" ]; then
        echo "  MISSING: $INPUT_FILE (sidx=$SOURCE_INDEX)" | tee -a "$LOG"; SHA_FAIL=1; continue
    fi
    ACTUAL=$(sha256sum "$INPUT_FILE" | awk '{print $1}')
    if [[ "$ACTUAL" != "$INPUT_SHA256"* && "$ACTUAL" != "$INPUT_SHA256" ]]; then
        echo "  SHA MISMATCH sidx=$SOURCE_INDEX: $INPUT_FILE" | tee -a "$LOG"
        echo "    expected prefix: $INPUT_SHA256" | tee -a "$LOG"
        echo "    got: $ACTUAL" | tee -a "$LOG"
        SHA_FAIL=1
    fi
done < "$MANIFEST"
[ "$SHA_FAIL" -eq 0 ] && echo "Input file SHA check: PASS" | tee -a "$LOG"
[ "$SHA_FAIL" -ne 0 ] && PREFLIGHT_FAIL=1

echo "" | tee -a "$LOG"

if [ "$PREFLIGHT_FAIL" -ne 0 ]; then
    echo "PREFLIGHT: FAIL — one or more checks failed; see above" | tee -a "$LOG"
    print_verdict "PREFLIGHT FAIL" "$LOG"; exit 1
fi

echo "PREFLIGHT: PASS" | tee -a "$LOG"

if [ "$DRY_RUN" -eq 1 ]; then
    echo "" | tee -a "$LOG"
    echo "DRY RUN — preflight complete; skipping receiver, container, and lar." | tee -a "$LOG"
    print_verdict "DRY-RUN PREFLIGHT PASS" "$LOG"; exit 0
fi

echo "" | tee -a "$LOG"

# ─────────────────────────────────────────────────────────────────────────────
# Start receiver
# ─────────────────────────────────────────────────────────────────────────────
echo "=== START RECEIVER ===" | tee -a "$LOG"

NUGRAPH_SOCKPATH="/dev/shm/nugraph_${MODE}_$$.sock"
export NUGRAPH_SOCKPATH

NUGRAPH_N_EVENTS=$(count_manifest_rows "$MANIFEST")
export NUGRAPH_N_EVENTS
export NUGRAPH_CONTAINER_SCRIPT

RECV_LOG="$OUTPUT_DIR/logs/receiver.log"

RECEIVER_ARGS=(
    --socket "$NUGRAPH_SOCKPATH"
    --output-h5 "$OUTPUT_H5"
    --expected-manifest "$RECEIVER_MANIFEST"
    --report "$REPORT"
    --timeout "$NUGRAPH_RECEIVER_TIMEOUT"
    --inter-session-timeout "$NUGRAPH_RECEIVER_INTER_SESSION_TIMEOUT"
    --max-sessions "$N_RECV_ROWS"
)

echo "Receiver args: ${RECEIVER_ARGS[*]}" | tee -a "$LOG"

PYTHONPATH="$NUGRAPH_PYWCML_DIR" \
"$NUGRAPH_NUML_PY" "$NUGRAPH_RECEIVER" \
    "${RECEIVER_ARGS[@]}" \
    > "$RECV_LOG" 2>&1 &
RECV_PID=$!
echo "Receiver PID: $RECV_PID" | tee -a "$LOG"

# Wait for socket to appear
wait_socket "$NUGRAPH_SOCKPATH" 120 "$LOG" || {
    echo "Receiver socket did not appear; killing receiver" | tee -a "$LOG"
    kill "$RECV_PID" 2>/dev/null || true
    print_verdict "RECEIVER SOCKET TIMEOUT" "$LOG"; exit 1
}

# ─────────────────────────────────────────────────────────────────────────────
# Run container
# ─────────────────────────────────────────────────────────────────────────────
echo "" | tee -a "$LOG"
echo "=== RUN CONTAINER ===" | tee -a "$LOG"

run_apptainer "$LOG"
CONTAINER_EXIT=$?
echo "Container exit: $CONTAINER_EXIT" | tee -a "$LOG"

# ─────────────────────────────────────────────────────────────────────────────
# Wait for receiver to finish
# Watchdog: if the receiver doesn't exit within RECEIVER_TIMEOUT+120s after the
# container, kill it. Needed because server_sock.accept() with settimeout() can
# hang indefinitely on some Lustre/socket configurations on Sophia.
# ─────────────────────────────────────────────────────────────────────────────
echo "" | tee -a "$LOG"
echo "=== WAIT RECEIVER ===" | tee -a "$LOG"
RECV_DEADLINE=$(( ${NUGRAPH_RECEIVER_TIMEOUT:-900} + 120 ))
echo "Receiver watchdog deadline: ${RECV_DEADLINE}s" | tee -a "$LOG"
(
    sleep "$RECV_DEADLINE"
    if kill -0 "$RECV_PID" 2>/dev/null; then
        echo "WATCHDOG: receiver PID $RECV_PID still running after ${RECV_DEADLINE}s; sending SIGTERM" | tee -a "$LOG"
        kill -TERM "$RECV_PID" 2>/dev/null || true
        sleep 15
        kill -KILL "$RECV_PID" 2>/dev/null || true
    fi
) &
WATCHDOG_PID=$!
wait "$RECV_PID"
RECV_EXIT=$?
kill "$WATCHDOG_PID" 2>/dev/null || true
wait "$WATCHDOG_PID" 2>/dev/null || true
echo "Receiver exit: $RECV_EXIT" | tee -a "$LOG"

# ─────────────────────────────────────────────────────────────────────────────
# POST-RUN AUDIT
# ─────────────────────────────────────────────────────────────────────────────
echo "" | tee -a "$LOG"
echo "=== POST-RUN AUDIT ===" | tee -a "$LOG"

AUDIT_FAIL=0

# 1. Output H5 exists
if [ ! -f "$OUTPUT_H5" ]; then
    echo "AUDIT FAIL: output H5 not found: $OUTPUT_H5" | tee -a "$LOG"; AUDIT_FAIL=1
else
    H5_SIZE=$(stat -c '%s' "$OUTPUT_H5")
    H5_SHA=$(sha256sum "$OUTPUT_H5" | awk '{print $1}')
    echo "Output H5: $OUTPUT_H5" | tee -a "$LOG"
    echo "  size: $H5_SIZE bytes" | tee -a "$LOG"
    echo "  SHA256: $H5_SHA" | tee -a "$LOG"
fi

# 2. .partial gate (post-run)
if ls "${OUTPUT_H5}.partial" 2>/dev/null | grep -q .; then
    echo "AUDIT FAIL: .partial file still exists — writer did not finalize cleanly" | tee -a "$LOG"
    AUDIT_FAIL=1
else
    echo ".partial gate (post-run): PASS" | tee -a "$LOG"
fi

# 3. Absent-file audit
check_absent_files "$OUTPUT_DIR" "$LOG" || AUDIT_FAIL=1

# 4. Receiver report
if [ -f "$REPORT" ]; then
    echo "Receiver report: $REPORT" | tee -a "$LOG"
    python3 -c "
import json, sys
with open('$REPORT') as f:
    r = json.load(f)
print(f\"  campaign_id: {r.get('campaign_id','?')}\")
print(f\"  events_received: {r.get('events_received','?')}\")
print(f\"  events_expected: {r.get('events_expected','?')}\")
print(f\"  status: {r.get('status','?')}\")
" | tee -a "$LOG" 2>/dev/null || echo "  (could not parse receiver report)" | tee -a "$LOG"
fi

# 5. Container and receiver exit codes
[ "$CONTAINER_EXIT" -ne 0 ] && { echo "AUDIT FAIL: container exited $CONTAINER_EXIT" | tee -a "$LOG"; AUDIT_FAIL=1; }
[ "$RECV_EXIT" -ne 0 ] && { echo "AUDIT FAIL: receiver exited $RECV_EXIT" | tee -a "$LOG"; AUDIT_FAIL=1; }

# Verdict
echo "" | tee -a "$LOG"
if [ "$AUDIT_FAIL" -eq 0 ]; then
    print_verdict "PASS" "$LOG"; exit 0
else
    print_verdict "FAIL" "$LOG"; exit 1
fi
