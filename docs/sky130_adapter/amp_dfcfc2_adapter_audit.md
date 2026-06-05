# amp_dfcfc2 AnalogGym-to-MAGICAL Adapter Audit

## Summary

- Case: `amp_dfcfc2`
- Top cell: `Leung_DFCFC2_Pin_3`
- Readiness: `blocked`
- Instances: 28
- Devices: `{"pfet": 13, "nfet": 13, "capacitor": 2}`
- Unsupported models: `{"sky130_fd_pr__cap_mim_m3_1": 2}`
- Unresolved params: 0

## Ports

- `gnda`: ground
- `vdda`: power
- `vinn`: differential_input_minus
- `vinp`: differential_input_plus
- `vout`: output
- `Ib`: bias

## Blockers

- `unsupported_device_models` (blocker): Some device models are not in MAGICAL's current Sky130 model support set.
- `large_case_for_first_adapter` (risk): The case is much larger than inverter_core/ota_core and should first pass a conversion-only smoke test.

## Model Counts

- `sky130_fd_pr__pfet_01v8`: 13 (supported)
- `sky130_fd_pr__nfet_01v8`: 13 (supported)
- `sky130_fd_pr__cap_mim_m3_1`: 2 (unsupported)

## Recommended Next Tasks

- Create an AnalogGym-to-MAGICAL conversion smoke test for the MOS-only subset.
- Evaluate W/L/M/nf expressions from AMP_DFCFC2_vars.spice and emit numeric MAGICAL parameters.
- Decide whether to map, approximate, black-box, or temporarily remove unsupported MIM capacitors.
- Only after conversion smoke passes, add amp_dfcfc2 as an experimental registry case.

## Conversion Smoke Result

- Strict policy `block`: stops conversion when `sky130_fd_pr__cap_mim_m3_1` appears.
- Experimental policy `omit-with-report`: emits a MOS-only MAGICAL netlist and records omitted capacitors.
- Real `amp_dfcfc2` result under `omit-with-report`: 26 MOS converted, 2 MIM capacitors omitted.
- MOS-only graph build result: 26 devices, 19 nets, 104 device-net edges.

The omitted-capacitor path is only a conversion smoke test. It is not a faithful circuit implementation and should not be used as final performance evidence.

## Sizing Set Decision

- Main V2 sizing set: 2026-05-21 bounded Top-K `rank=1` TT candidate.
- Baseline/sanity sizing set: AnalogGym default `AMP_DFCFC2_vars.spice`.
- Do not use the 2026-04-12 GRPO `recommended_candidates.json` for V2, because that run has no recommended candidate records.

The rank1 candidate is materialized from:

`/home/qlf/IOT/agent_workflow/workstreams/2026-05-21_analoggym_opt_bounded_topk_candidates/training_saves/bounded_topk_amp_dfcfc2_20260521-100537/recommended_candidates_tt/recommended_candidates.json`

Materialized artifacts are generated under:

`generated/analoggym_adapter_audits/amp_dfcfc2/bounded_topk_rank1/`

Rank1 summary:

- `rank=1`
- `evaluation_source=tt`
- `pm_feasible=true`
- `reward=-0.75`
- `phase_margin=76.80349`
- `dcgain=128.6176`
- `GBW=948140.8`
- `Power=0.63671382`
- parameter count: 27

Rank1 conversion result:

- Strict `block` policy still stops at the unsupported MIM capacitors.
- Experimental `omit-with-report` policy converts 26 MOS instances and omits 2 MIM capacitors.
- Rank1 MOS-only graph build result: 26 devices, 19 nets, 104 device-net edges.

## Adapter Harness Decision

Unsupported MIM capacitors are now represented as an adapter-level Harness decision, not only as a converter error message. The goal is to make future AnalogGym netlist conversions machine-checkable:

```text
conversion_report.json
-> adapter_harness_decision.json
-> decide whether this conversion is final-flow safe or only a smoke test
```

For `sky130_fd_pr__cap_mim_m3_1`, the current Harness policy is:

- known category: `mim_capacitor`
- smoke allowed: `true`
- final flow allowed: `false`
- recommended actions:
  - `add_mim_cap_mapping`
  - `use_black_box_macro`
  - `block_final_pipeline_until_supported`

Rank1 real-case decisions:

- strict `block` conversion report -> `decision=block_final_flow`
- experimental `omit-with-report` conversion report -> `decision=smoke_only_not_final`

This means the MOS-only path remains useful for adapter smoke testing, but Harness must prevent it from being mistaken for a faithful layout or post-layout performance result.

## MIM Proxy Mapping Result

MAGICAL already supports generic capacitor primitives `cfmom` and `cfmom_2t`. The V2 adapter now has an experimental policy:

```text
--unsupported-cap-policy map-mim-to-cfmom-2t
```

For `sky130_fd_pr__cap_mim_m3_1`, this policy emits a `cfmom_2t` proxy and records the mapping in `mapped_instances`.

Real rank1 result:

- converted MOS instances: 26
- mapped MIM proxy instances: 2
- omitted instances: 0
- Harness decision: `mapped_requires_validation`
- smoke allowed: `true`
- final flow allowed: `false`

MAGICAL placement/routing smoke result:

- MAGICAL Docker run completed and wrote `Leung_DFCFC2_Pin_3.route.gds`.
- MAGICAL generated capacitor PCell GDS files for both proxy capacitors.
- Route-log Harness status is `completed_with_route_warnings`.
- The route log reports a failed/unresolved route net: `net31`.

Full backend pipeline attempt:

- MAGICAL, GDS remap, pin label, and pin shape stages completed.
- Magic DRC failed before real DRC because local Magic `8.3.105` cannot parse the current sky130A techfile.
- Environment diagnosis reports `magic_pdk_incompatibility`.

The proxy mapping is documented in `docs/sky130_adapter/mim_cap_mapping_decision.md`. It is better than omitting the capacitor for adapter smoke, but it is still not a PDK-exact MIM implementation. Final flow remains blocked until the route warning is resolved and the mapped capacitor passes DRC/LVS/PEX validation in a compatible Magic/PDK environment, or is replaced by a proper Sky130 MIM strategy.

## Interpretation

`amp_dfcfc2` is a useful V2 target, but it is not ready to enter the existing MAGICAL Sky130 pipeline directly. The MOS devices use supported Sky130 1.8 V model names, and both the default vars file and the bounded Top-K rank1 vars can resolve the observed symbolic W/L/M expressions. The main adapter blocker is the MIM capacitor model `sky130_fd_pr__cap_mim_m3_1`, which is not in the current MAGICAL Sky130 support set. The next safe step is therefore MIM capacitor support or a black-box/macro strategy before adding the case to the main registry as a faithful circuit.
