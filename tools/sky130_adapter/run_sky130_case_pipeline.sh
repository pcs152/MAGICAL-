#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DOCKER_IMAGE="${DOCKER_IMAGE:-jayl940712/magical:latest}"

DEFAULT_PDK_ROOT="$HOME/.ciel/ciel/sky130/versions/7b70722e33c03fcb5dabcf4d479fb0822d9251c9"
DEFAULT_SKY130A="$DEFAULT_PDK_ROOT/sky130A"
SKY130A="${SKY130A:-$DEFAULT_SKY130A}"
PDK_ROOT="${PDK_ROOT:-$(dirname "$SKY130A")}"
export PDK_ROOT
MAGICRC="$SKY130A/libs.tech/magic/sky130A.magicrc"
NETGEN_SETUP="$SKY130A/libs.tech/netgen/sky130A_setup.tcl"

usage() {
    cat <<'EOF'
Usage:
  run_sky130_case_pipeline.sh \
    --case-dir <dir> \
    --top-cell <cell> \
    --magical-netlist <file> \
    --config <file> \
    --vdd <net> \
    --vss <net> \
    --out-dir <dir> \
    [--raw-netlist <file>] \
    [--convert-xschem yes|no] \
    [--case-name <name>] \
    [--output-node <net>] \
    [--net-role <net=role>]

Paths may be absolute or relative to the repository root. File paths under
--case-dir may be passed as basenames.
EOF
}

CASE_DIR_ARG=""
CASE_NAME=""
TOP_CELL=""
RAW_NETLIST_ARG=""
MAGICAL_NETLIST_ARG=""
CONFIG_ARG=""
VDD_NET=""
VSS_NET=""
OUT_DIR_ARG=""
CONVERT_XSCHEM="no"
OUTPUT_NODE=""
NET_ROLES=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --case-dir) CASE_DIR_ARG="$2"; shift 2 ;;
        --case-name) CASE_NAME="$2"; shift 2 ;;
        --top-cell) TOP_CELL="$2"; shift 2 ;;
        --raw-netlist) RAW_NETLIST_ARG="$2"; shift 2 ;;
        --magical-netlist) MAGICAL_NETLIST_ARG="$2"; shift 2 ;;
        --config) CONFIG_ARG="$2"; shift 2 ;;
        --vdd) VDD_NET="$2"; shift 2 ;;
        --vss) VSS_NET="$2"; shift 2 ;;
        --out-dir) OUT_DIR_ARG="$2"; shift 2 ;;
        --convert-xschem) CONVERT_XSCHEM="$2"; shift 2 ;;
        --output-node) OUTPUT_NODE="$2"; shift 2 ;;
        --net-role) NET_ROLES+=("$2"); shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "error: unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

[[ -n "$CASE_DIR_ARG" ]] || { echo "error: --case-dir is required" >&2; exit 2; }
[[ -n "$TOP_CELL" ]] || { echo "error: --top-cell is required" >&2; exit 2; }
[[ -n "$MAGICAL_NETLIST_ARG" ]] || { echo "error: --magical-netlist is required" >&2; exit 2; }
[[ -n "$CONFIG_ARG" ]] || { echo "error: --config is required" >&2; exit 2; }
[[ -n "$VDD_NET" ]] || { echo "error: --vdd is required" >&2; exit 2; }
[[ -n "$VSS_NET" ]] || { echo "error: --vss is required" >&2; exit 2; }
[[ -n "$OUT_DIR_ARG" ]] || { echo "error: --out-dir is required" >&2; exit 2; }
[[ "$CONVERT_XSCHEM" == "yes" || "$CONVERT_XSCHEM" == "no" ]] || { echo "error: --convert-xschem must be yes or no" >&2; exit 2; }

resolve_dir() {
    local path="$1"
    if [[ "$path" = /* ]]; then
        echo "$path"
    else
        echo "$REPO_ROOT/$path"
    fi
}

resolve_case_file() {
    local path="$1"
    if [[ "$path" = /* ]]; then
        echo "$path"
    elif [[ "$path" == */* ]]; then
        echo "$REPO_ROOT/$path"
    else
        echo "$CASE_DIR/$path"
    fi
}

rel_to_repo() {
    local path="$1"
    python3 - "$REPO_ROOT" "$path" <<'PY'
import os
import sys
root, path = sys.argv[1:3]
print(os.path.relpath(path, root))
PY
}

CASE_DIR="$(resolve_dir "$CASE_DIR_ARG")"
OUT_DIR="$(resolve_dir "$OUT_DIR_ARG")"
MAGICAL_NETLIST="$(resolve_case_file "$MAGICAL_NETLIST_ARG")"
CONFIG="$(resolve_case_file "$CONFIG_ARG")"
RAW_NETLIST=""
if [[ -n "$RAW_NETLIST_ARG" ]]; then
    RAW_NETLIST="$(resolve_case_file "$RAW_NETLIST_ARG")"
fi
[[ -n "$CASE_NAME" ]] || CASE_NAME="$TOP_CELL"

MAGIC_CELL="${TOP_CELL}_flat"
SUMMARY="$OUT_DIR/summary.md"
CONVERT_LOG="$OUT_DIR/convert.log"
POWERNET_CONFIG_REPORT="$OUT_DIR/powernet_config_check.md"
MAGICAL_LOG="$OUT_DIR/magical_place_route.log"
MAGICAL_RUN_LOG="$CASE_DIR/run_${TOP_CELL}_trial.log"
REMAP_REPORT="$OUT_DIR/gds_remap_report.md"
LABEL_REPORT="$OUT_DIR/pin_label_report.md"
SHAPE_REPORT="$OUT_DIR/pin_shape_report.md"
DRC_TCL="$OUT_DIR/magic_drc.tcl"
DRC_LOG="$OUT_DIR/magic_drc.log"
MAGIC_TCL="$OUT_DIR/magic_extract.tcl"
MAGIC_LOG="$OUT_DIR/magic_extract.log"
EXTRACTED_LVS="$OUT_DIR/${TOP_CELL}_extracted.spice"
LVS_PREP_REPORT="$OUT_DIR/lvs_preparation_report.md"
NETGEN_LOG="$OUT_DIR/netgen_lvs.log"
NETGEN_REPORT="$OUT_DIR/netgen_lvs_report.out"
LVS_RESULT_SUMMARY="$OUT_DIR/lvs_result_summary.md"
PEX_SUMMARY="$OUT_DIR/pex_summary.md"
PARASITIC_SUMMARY_JSON="$OUT_DIR/parasitic_summary.json"
CIRCUIT_GRAPH_JSON="$OUT_DIR/circuit_graph.json"
SAMPLE_RECORD_JSON="$OUT_DIR/sample_record.json"

mkdir -p "$OUT_DIR"

summary_fail() {
    local stage="$1"
    local message="$2"
    {
        echo "# Sky130 Case Pipeline Summary"
        echo
        echo "| Field | Value |"
        echo "| --- | --- |"
        echo "| CASE_NAME | $CASE_NAME |"
        echo "| TOP_CELL | $TOP_CELL |"
        echo "| VDD_NET | $VDD_NET |"
        echo "| VSS_NET | $VSS_NET |"
        echo "| STATUS | FAIL |"
        echo "| FAILED_STAGE | $stage |"
        echo "| MESSAGE | $message |"
    } > "$SUMMARY"
    echo "FAIL[$stage]: $message" >&2
    exit 1
}

require_file() {
    [[ -f "$1" ]] || summary_fail "$2" "required file not found: $1"
}

command -v docker >/dev/null 2>&1 || summary_fail "setup" "Docker is required for MAGICAL placement/routing stage."
command -v magic >/dev/null 2>&1 || summary_fail "setup" "magic command not found in PATH"

NETGEN_CMD=""
if command -v netgen >/dev/null 2>&1; then
    NETGEN_CMD="$(command -v netgen)"
elif command -v netgen-lvs >/dev/null 2>&1; then
    NETGEN_CMD="$(command -v netgen-lvs)"
else
    summary_fail "setup" "neither netgen nor netgen-lvs command was found in PATH"
fi

require_file "$CONFIG" "setup"
require_file "$MAGICRC" "setup"
require_file "$NETGEN_SETUP" "setup"
if [[ "$CONVERT_XSCHEM" == "yes" ]]; then
    [[ -n "$RAW_NETLIST" ]] || summary_fail "setup" "--raw-netlist is required when --convert-xschem yes"
    require_file "$RAW_NETLIST" "setup"
else
    require_file "$MAGICAL_NETLIST" "setup"
fi

if [[ "$CONVERT_XSCHEM" == "yes" ]]; then
    echo "RUN: convert xschem Sky130 netlist"
    python3 "$SCRIPT_DIR/convert_xschem_sky130_netlist.py" \
        --input "$RAW_NETLIST" \
        --output "$MAGICAL_NETLIST" \
        --global-port "$VSS_NET" \
        > "$CONVERT_LOG" 2>&1 || summary_fail "convert" "xschem-to-MAGICAL conversion failed; see $CONVERT_LOG"
fi
require_file "$MAGICAL_NETLIST" "setup"

echo "RUN: build circuit graph from MAGICAL netlist"
python3 "$SCRIPT_DIR/build_circuit_graph.py" \
    --input "$MAGICAL_NETLIST" \
    --output "$CIRCUIT_GRAPH_JSON" \
    --top-cell "$TOP_CELL" >/dev/null || summary_fail "circuit_graph" "circuit graph generation failed"

echo "RUN: check explicit power-net config"
set +e
python3 "$SCRIPT_DIR/sky130_case_pipeline_helpers.py" check-power-nets \
    --config "$CONFIG" \
    --vdd "$VDD_NET" \
    --vss "$VSS_NET" \
    > "$POWERNET_CONFIG_REPORT" 2>&1
power_check_status=$?
set -e
if [[ "$power_check_status" -ne 0 ]]; then
    summary_fail "power_config" "config does not contain requested vddNetNames/vssNetNames; see $POWERNET_CONFIG_REPORT"
fi

CASE_REL="$(rel_to_repo "$CASE_DIR")"
CONFIG_BASE="$(basename "$CONFIG")"

echo "RUN: MAGICAL placement/routing in Docker"
docker run --rm \
    -v "$REPO_ROOT:/MAGICAL" \
    "$DOCKER_IMAGE" \
    bash -lc "export PYTHONPATH=/usr/local/lib/python3.7/site-packages:/MAGICAL/flow/python:\${PYTHONPATH:-}; cd /MAGICAL/${CASE_REL} && rm -rf ${TOP_CELL}.route.gds ${TOP_CELL}.place.gds ${TOP_CELL}.ioPin gds && mkdir -p gds && python3.7 /MAGICAL/flow/python/Magical.py ${CONFIG_BASE} > run_${TOP_CELL}_trial.log 2>&1" \
    > "$MAGICAL_LOG" 2>&1 || summary_fail "magical_place_route" "MAGICAL failed; see $MAGICAL_LOG and $MAGICAL_RUN_LOG"

ROUTE_GDS="$CASE_DIR/${TOP_CELL}.route.gds"
IOPIN="$CASE_DIR/${TOP_CELL}.ioPin"
SKY130_GDS="$CASE_DIR/${TOP_CELL}.sky130.gds"
PINNED_GDS="$CASE_DIR/${TOP_CELL}.sky130.pinned.gds"
PINNED_SHAPES_GDS="$CASE_DIR/${TOP_CELL}.sky130.pinned_shapes.gds"

require_file "$ROUTE_GDS" "magical_output"
require_file "$IOPIN" "magical_output"

echo "RUN: remap GDS"
python3 "$SCRIPT_DIR/remap_gds_to_sky130.py" \
    --input-gds "$ROUTE_GDS" \
    --output-gds "$SKY130_GDS" \
    --report "$REMAP_REPORT" >/dev/null || summary_fail "gds_remap" "GDS remap failed"

echo "RUN: add Sky130 pin labels"
python3 "$SCRIPT_DIR/add_sky130_pin_labels_from_iopin.py" \
    --input-gds "$SKY130_GDS" \
    --iopin "$IOPIN" \
    --output-gds "$PINNED_GDS" \
    --report "$LABEL_REPORT" \
    --cell "$MAGIC_CELL" \
    --netlist "$MAGICAL_NETLIST" \
    --top-cell "$TOP_CELL" \
    --only-top-ports >/dev/null || summary_fail "pin_labels" "pin label postprocess failed"

echo "RUN: add Sky130 pin shapes"
python3 "$SCRIPT_DIR/add_sky130_pin_shapes_from_iopin.py" \
    --input-gds "$PINNED_GDS" \
    --iopin "$IOPIN" \
    --output-gds "$PINNED_SHAPES_GDS" \
    --report "$SHAPE_REPORT" \
    --cell "$MAGIC_CELL" \
    --netlist "$MAGICAL_NETLIST" \
    --top-cell "$TOP_CELL" \
    --only-top-ports >/dev/null || summary_fail "pin_shapes" "pin shape postprocess failed"

PINNED_SHAPES_REL="$(rel_to_repo "$PINNED_SHAPES_GDS")"

cat > "$DRC_TCL" <<EOF
puts "SKY130_CASE_DRC: reading pinned-shapes GDS"
gds read $PINNED_SHAPES_REL
if {[catch {load ${MAGIC_CELL}} load_error]} {
    puts stderr "ERROR: failed to load ${MAGIC_CELL}"
    puts stderr \$load_error
    quit -noprompt
}
drc check
drc count
quit -noprompt
EOF

echo "RUN: Magic DRC"
(cd "$REPO_ROOT" && magic -dnull -noconsole -rcfile "$MAGICRC" < "$DRC_TCL" > "$DRC_LOG" 2>&1) || summary_fail "magic_drc" "Magic DRC command failed; see $DRC_LOG"

cat > "$MAGIC_TCL" <<EOF
puts "SKY130_CASE_LVS: reading pinned-shapes GDS"
gds read $PINNED_SHAPES_REL
if {[catch {load ${MAGIC_CELL}} load_error]} {
    puts stderr "ERROR: failed to load ${MAGIC_CELL}"
    puts stderr \$load_error
    quit -noprompt
}
select top cell
extract all
ext2spice lvs
ext2spice cthresh 0
ext2spice rthresh 0
ext2spice
quit -noprompt
EOF

rm -f "$REPO_ROOT/${MAGIC_CELL}.spice" "$REPO_ROOT/${MAGIC_CELL}.sp" "$REPO_ROOT/${MAGIC_CELL}.ext"
echo "RUN: Magic extraction"
(cd "$REPO_ROOT" && magic -dnull -noconsole -rcfile "$MAGICRC" < "$MAGIC_TCL" > "$MAGIC_LOG" 2>&1) || summary_fail "magic_extract" "Magic extraction command failed; see $MAGIC_LOG"

found_spice=""
for candidate in "$REPO_ROOT/${MAGIC_CELL}.spice" "$REPO_ROOT/${MAGIC_CELL}.sp"; do
    if [[ -f "$candidate" ]]; then
        found_spice="$candidate"
        break
    fi
done
[[ -n "$found_spice" ]] || summary_fail "magic_extract" "Magic did not produce ${MAGIC_CELL}.spice"
mv "$found_spice" "$EXTRACTED_LVS"
if [[ -f "$REPO_ROOT/${MAGIC_CELL}.ext" ]]; then
    mv "$REPO_ROOT/${MAGIC_CELL}.ext" "$OUT_DIR/${MAGIC_CELL}.ext"
fi

echo "RUN: prepare raw/connectivity LVS netlists"
python3 "$SCRIPT_DIR/prepare_lvs_netlists.py" \
    --source "$MAGICAL_NETLIST" \
    --extracted "$EXTRACTED_LVS" \
    --out-dir "$OUT_DIR" \
    --prefix "$TOP_CELL" \
    --report "$LVS_PREP_REPORT" >/dev/null || summary_fail "lvs_prepare" "LVS preparation failed"

CONNECTIVITY_SOURCE="$OUT_DIR/${TOP_CELL}_source.connectivity.spice"
CONNECTIVITY_EXTRACTED="$OUT_DIR/${TOP_CELL}_extracted.connectivity.spice"
RAW_EXTRACTED_COPY="$OUT_DIR/${TOP_CELL}_extracted.raw.spice"

echo "RUN: Netgen connectivity LVS"
set +e
"$NETGEN_CMD" -batch lvs \
    "$CONNECTIVITY_SOURCE $TOP_CELL" \
    "$CONNECTIVITY_EXTRACTED $MAGIC_CELL" \
    "$NETGEN_SETUP" \
    "$NETGEN_REPORT" \
    > "$NETGEN_LOG" 2>&1
netgen_status=$?
set -e

echo "RUN: analyze LVS result"
set +e
python3 "$SCRIPT_DIR/analyze_lvs_result.py" \
    --report "$NETGEN_REPORT" \
    --log "$NETGEN_LOG" \
    --output "$LVS_RESULT_SUMMARY" >/dev/null
analyze_status=$?
set -e

echo "RUN: summarize Magic PEX"
pex_args=(
    --input "$RAW_EXTRACTED_COPY"
    --output "$PEX_SUMMARY"
    --json-output "$PARASITIC_SUMMARY_JSON"
    --case-name "$CASE_NAME"
    --top-cell "$TOP_CELL"
)
if [[ -n "$OUTPUT_NODE" ]]; then
    pex_args+=(--output-node "$OUTPUT_NODE")
fi
for net_role in "${NET_ROLES[@]}"; do
    pex_args+=(--net-role "$net_role")
done
python3 "$SCRIPT_DIR/summarize_magic_pex.py" "${pex_args[@]}" >/dev/null || summary_fail "pex_summary" "PEX summary failed"

subckt_line="$(grep -E "^[[:space:]]*\\.subckt[[:space:]]+${MAGIC_CELL}" "$EXTRACTED_LVS" | head -n 1 || true)"
raw_subckt_ports="$(python3 "$SCRIPT_DIR/sky130_case_pipeline_helpers.py" subckt-ports --line "$subckt_line")"
anon_nodes="$(grep -Eo 'a_[[:alnum:]_]+#|w_[[:alnum:]_]+#' "$EXTRACTED_LVS" | sort -u | paste -sd ', ' - || true)"
[[ -n "$anon_nodes" ]] || anon_nodes="none"
drc_count="$(awk '/Total DRC errors found:/ {print $NF}' "$DRC_LOG" | tail -n 1)"
[[ -n "$drc_count" ]] || drc_count="unknown"
pex_caps="$(awk -F': ' '/Parasitic capacitor count:/ {print $2}' "$PEX_SUMMARY" | tail -n 1)"
[[ -n "$pex_caps" ]] || pex_caps="unknown"
pex_total="$(awk -F': ' '/Total listed capacitance:/ {print $2}' "$PEX_SUMMARY" | tail -n 1)"
[[ -n "$pex_total" ]] || pex_total="unknown"
lvs_match="no"
if [[ "$netgen_status" -eq 0 && "$analyze_status" -eq 0 ]] && grep -q "LVS status: \\*\\*PASS\\*\\*" "$LVS_RESULT_SUMMARY"; then
    lvs_match="yes"
elif grep -q "Circuits match uniquely" "$NETGEN_REPORT" && grep -q "Netlists match uniquely" "$NETGEN_REPORT"; then
    lvs_match="yes"
fi
net_renames_used="no"
grep -q 'Net rename enabled: no' "$LVS_PREP_REPORT" || net_renames_used="yes"

cat > "$SUMMARY" <<EOF
# Sky130 Case Pipeline Summary

| Field | Value |
| --- | --- |
| CASE_NAME | $CASE_NAME |
| TOP_CELL | $TOP_CELL |
| VDD_NET | $VDD_NET |
| VSS_NET | $VSS_NET |
| MAGICAL_RESULT | pass |
| GDS_REMAP_RESULT | pass |
| PIN_LABEL_RESULT | pass |
| PIN_SHAPE_RESULT | pass |
| DRC_COUNT | $drc_count |
| RAW_SUBCKT_PORTS | $raw_subckt_ports |
| ANONYMOUS_NODES | $anon_nodes |
| CONNECTIVITY_LVS_MATCH | $lvs_match |
| NETGEN_EXIT_STATUS | $netgen_status |
| NET_RENAMES_USED | $net_renames_used |
| PEX_CAPS | $pex_caps |
| PEX_TOTAL_CAP_FF | $pex_total |
| PEX_OUTPUT_NODE | ${OUTPUT_NODE:-none} |

## KEY_OUTPUTS

- Case directory: \`$CASE_DIR\`
- Source/MAGICAL netlist: \`$MAGICAL_NETLIST\`
- Config: \`$CONFIG\`
- MAGICAL log: \`$MAGICAL_LOG\`
- MAGICAL run log: \`$MAGICAL_RUN_LOG\`
- ioPin: \`$IOPIN\`
- Route GDS: \`$ROUTE_GDS\`
- Sky130 remapped GDS: \`$SKY130_GDS\`
- Pinned-shapes GDS: \`$PINNED_SHAPES_GDS\`
- DRC log: \`$DRC_LOG\`
- Raw extracted netlist: \`$EXTRACTED_LVS\`
- Raw extracted netlist copy: \`$RAW_EXTRACTED_COPY\`
- Connectivity source netlist: \`$CONNECTIVITY_SOURCE\`
- Connectivity extracted netlist: \`$CONNECTIVITY_EXTRACTED\`
- LVS preparation report: \`$LVS_PREP_REPORT\`
- Netgen connectivity LVS report: \`$NETGEN_REPORT\`
- LVS result summary: \`$LVS_RESULT_SUMMARY\`
- PEX summary: \`$PEX_SUMMARY\`
- Parasitic JSON summary: \`$PARASITIC_SUMMARY_JSON\`
- Circuit graph JSON: \`$CIRCUIT_GRAPH_JSON\`
EOF

echo "RUN: build graph-learning sample record"
python3 "$SCRIPT_DIR/build_sample_record.py" \
    --case-name "$CASE_NAME" \
    --top-cell "$TOP_CELL" \
    --vdd "$VDD_NET" \
    --vss "$VSS_NET" \
    --case-dir "$CASE_DIR" \
    --out-dir "$OUT_DIR" \
    --source-netlist "$MAGICAL_NETLIST" \
    --final-gds "$PINNED_SHAPES_GDS" \
    --raw-extracted-netlist "$RAW_EXTRACTED_COPY" \
    --circuit-graph "$CIRCUIT_GRAPH_JSON" \
    --parasitic-summary "$PARASITIC_SUMMARY_JSON" \
    --summary "$SUMMARY" \
    --output "$SAMPLE_RECORD_JSON" \
    --repo-root "$REPO_ROOT" >/dev/null || summary_fail "sample_record" "sample record generation failed"

cat >> "$SUMMARY" <<EOF
- Graph-learning sample record: \`$SAMPLE_RECORD_JSON\`
EOF

echo "Summary written: $SUMMARY"
echo "CASE_NAME=$CASE_NAME"
echo "TOP_CELL=$TOP_CELL"
echo "RAW_SUBCKT_PORTS=$raw_subckt_ports"
echo "ANONYMOUS_NODES=$anon_nodes"
echo "DRC_COUNT=$drc_count"
echo "CONNECTIVITY_LVS_MATCH=$lvs_match"
echo "NET_RENAMES_USED=$net_renames_used"
echo "PEX_CAPS=$pex_caps"
echo "PEX_TOTAL_CAP_FF=$pex_total"
echo "CIRCUIT_GRAPH_JSON=$CIRCUIT_GRAPH_JSON"
echo "SAMPLE_RECORD_JSON=$SAMPLE_RECORD_JSON"

[[ "$lvs_match" == "yes" ]] || summary_fail "connectivity_lvs" "Connectivity LVS did not pass; see $LVS_RESULT_SUMMARY"
