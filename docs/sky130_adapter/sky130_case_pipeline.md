# Sky130 Case Pipeline

## Why This Exists

The inverter and OTA Sky130 trials proved the same sequence twice: MAGICAL
placement/routing, GDS remap, Sky130 pin postprocess, Magic DRC/extraction,
Netgen connectivity LVS, and raw PEX summary. Keeping that logic in separate
scripts makes the next test netlist harder to add and easier to drift.

`tools/sky130_adapter/run_sky130_case_pipeline.sh` is the shared case runner.
The existing inverter and OTA entrypoints remain as wrappers so old commands
still work, while the core flow now has one implementation.

## Required Case Inputs

Each case needs a dedicated directory, normally under `examples/`:

```text
examples/<case_name>/
  <top_cell>.json
  <source_or_magical_netlist>.sp
```

For xschem-derived cases, keep both the raw input and converted MAGICAL netlist:

```text
examples/<case_name>/
  <top_cell>_raw.spice
  <top_cell>_magical.sp
  <top_cell>.json
```

The config must point at the MAGICAL-readable netlist and the trial Sky130 PDK
files. It must also explicitly name power nets:

```json
"vddNetNames" : ["VDD"],
"vssNetNames" : ["GND"]
```

For the inverter case, these are `VPWR` and `VGND`.

## Command Shape

Example OTA invocation:

```bash
tools/sky130_adapter/run_sky130_case_pipeline.sh \
  --case-name ota_core \
  --case-dir examples/ota_core_sky130_try \
  --top-cell ota_core \
  --raw-netlist ota_core_raw.spice \
  --magical-netlist ota_core_magical.sp \
  --config ota_core.json \
  --vdd VDD \
  --vss GND \
  --out-dir generated/sky130_cases/ota_core \
  --convert-xschem yes
```

Example inverter invocation:

```bash
tools/sky130_adapter/run_sky130_case_pipeline.sh \
  --case-name inverter_core \
  --case-dir examples/inverter_sky130_try \
  --top-cell inverter_core \
  --magical-netlist inverter_sky130_name_test.sp \
  --config inverter_trial.json \
  --vdd VPWR \
  --vss VGND \
  --out-dir generated/sky130_cases/inverter_core \
  --convert-xschem no
```

Paths may be absolute or relative to the repository root. Netlist/config
basenames are resolved inside `--case-dir`.

## Xschem Conversion

When `--convert-xschem yes` is set, the pipeline calls:

```text
tools/sky130_adapter/convert_xschem_sky130_netlist.py
```

The raw xschem/ngspice input is converted to MAGICAL syntax before placement.
The pipeline passes the selected VSS net as the global port so cases like OTA
keep `GND` explicit in the top subckt port list.

## Power-Net Config

MAGICAL must see `vddNetNames` and `vssNetNames` in the config. The inverter
debugging showed that missing power-net recognition can turn a real source or
bulk connection into an anonymous extracted node. The generic pipeline checks
that the requested `--vdd` and `--vss` names are present before running MAGICAL;
it reports a setup failure instead of silently continuing.

## Top-Port Filter

MAGICAL `ioPin` may include internal routed nets. The OTA trial exposed this
with `net1` and `net2`. The generic pipeline always calls the Sky130 label and
pin-shape postprocess with:

```text
--netlist <magical netlist>
--top-cell <top cell>
--only-top-ports
```

Only names in the source top subckt port list become Sky130 pins. Internal
`ioPin` entries are skipped and reported, so they are not promoted into Magic's
raw `.subckt` interface.

## LVS and PEX Split

The flow preserves the raw Magic extraction, including parasitic capacitors, in:

```text
<out-dir>/<top_cell>_extracted.raw.spice
```

It separately prepares connectivity-only source and extracted netlists for
Netgen. This keeps the current LVS claim narrow: connectivity LVS, not
parasitic-aware LVS. PEX information remains available through:

```text
<out-dir>/pex_summary.md
<out-dir>/parasitic_summary.json
```

The graph-learning V0 layer also records the pre-layout circuit graph and
links it to the true Magic PEX labels:

```text
<out-dir>/circuit_graph.json
<out-dir>/sample_record.json
<out-dir>/risk_report.json
<out-dir>/harness_decision.json
```

## Summary Format

Every case writes:

```text
<out-dir>/summary.md
```

with at least these fields:

```text
CASE_NAME
TOP_CELL
VDD_NET
VSS_NET
MAGICAL_RESULT
GDS_REMAP_RESULT
PIN_LABEL_RESULT
PIN_SHAPE_RESULT
DRC_COUNT
RAW_SUBCKT_PORTS
ANONYMOUS_NODES
CONNECTIVITY_LVS_MATCH
NET_RENAMES_USED
PEX_CAPS
PEX_TOTAL_CAP_FF
CIRCUIT_GRAPH_JSON
SAMPLE_RECORD_JSON
RISK_REPORT_JSON
HARNESS_DECISION_JSON
KEY_OUTPUTS
```

## Adding the Next Case

Recommended layout:

```text
examples/<new_case>/
  <new_case>_raw.spice        # if starting from xschem/ngspice
  <top_cell>_magical.sp       # converted or handwritten MAGICAL input
  <top_cell>.json
generated/sky130_cases/<new_case>/
docs/sky130_adapter/<new_case>_trial.md
```

Start by making the netlist/config pair work through the generic pipeline. Keep
new outputs in `generated/sky130_cases/<new_case>/` and document whether DRC,
connectivity LVS, and PEX summary pass. Do not treat layer/datatype remap as
equivalent to a complete native Sky130 adaptation.
