# Sky130 MIM Capacitor Mapping Decision

## Summary

AnalogGym `amp_dfcfc2` contains two `sky130_fd_pr__cap_mim_m3_1` instances. MAGICAL does not directly recognize this Sky130 PDK device name, but the MAGICAL parser and examples already support generic capacitor primitives:

- `cfmom`
- `cfmom_2t`

For V2 adapter smoke testing, the converter may map `sky130_fd_pr__cap_mim_m3_1` to MAGICAL `cfmom_2t`. This is a proxy mapping, not a PDK-exact MIM replacement.

## Evidence In MAGICAL

MAGICAL capacitor support appears in:

- `flow/python/DesignDB.py`: `capacitor_set = {"cfmom", "cfmom_2t"}`
- `flow/python/Device_generator.py`: `ImplTypePCELL_Cap` creates a MAGICAL capacitor PCell.
- `examples/adc1/CTDSM_TOP.sp`, `examples/adc2/CTDSM_CORE_NEW_hspice.sp`, `examples/ota1/ota1.sp`: existing `cfmom_2t` examples.

This means the adapter should prefer a MAGICAL-native capacitor proxy before omitting MIM capacitors.

## Mapping Rule

Source instance:

```spice
XC0 net050 vout sky130_fd_pr__cap_mim_m3_1 W=30 L=30 MF=M_C0 m=M_C0
```

Mapped instance:

```spice
C0 (net050 vout) cfmom_2t nr=<MF> lr=<L> w=70n s=70n stm=2 spm=6 multi=<m> ftip=140n
```

Current policy:

- `MF` maps to `nr`.
- `L` maps to `lr`.
- `m` maps to `multi`.
- `w=70n`, `s=70n`, `stm=2`, `spm=6`, `ftip=140n` follow existing MAGICAL `cfmom_2t` example conventions.

The source `W` is not treated as a direct `cfmom_2t w` value in V2 because AnalogGym's Sky130 MIM plate geometry is not equivalent to MAGICAL's generic `cfmom_2t` finger width parameter.

## Harness Policy

The adapter Harness treats this mapping as:

- `smoke_allowed = true`
- `final_flow_allowed = false`
- `decision = mapped_requires_validation`

This lets us keep moving on adapter and graph-sample infrastructure while preventing the proxy from being mistaken for final layout or post-layout performance evidence.

Required validation before final flow:

- Run MAGICAL placement/routing with the mapped capacitor.
- Run Magic DRC.
- Run Netgen LVS and confirm the mapped capacitor does not break connectivity comparison.
- Run Magic extraction and inspect the resulting PEX netlist.
- Compare the proxy mapping against Sky130 MIM requirements or replace it with a proper macro/PDK-specific flow.

## Real DFCFC2 Rank1 Smoke Result

Command policy:

```bash
--unsupported-cap-policy map-mim-to-cfmom-2t
```

Local generated result:

- converted MOS instances: 26
- mapped MIM proxy instances: 2
- omitted instances: 0
- Harness decision: `mapped_requires_validation`

MAGICAL placement/routing smoke:

- Docker image: `jayl940712/magical:latest`
- route GDS written: `true`
- capacitor PCell GDS generated: `Leung_DFCFC2_Pin_3_C0.gds`, `Leung_DFCFC2_Pin_3_C1.gds`
- route-log status: `completed_with_route_warnings`
- failed route net detected by log Harness: `net31`
- final flow allowed by route-log Harness: `false`

This means MAGICAL can parse the mapped `cfmom_2t` proxy, generate capacitor layouts, place the full DFCFC2 case, and write a routed GDS. However, the routing log still contains a failed-net warning, so the result remains a smoke result rather than a final layout.

Fixed-env backend pipeline attempt:

- environment entry: `scripts/env/magical_sky130_env.sh`
- Magic path: `/home/qlf/IOT/scripts/env/bin/magic`
- Magic version through wrapper: `8.3.483`
- sky130A PDK hash: `7b70722e33c03fcb5dabcf4d479fb0822d9251c9`
- MAGICAL placement/routing: passed
- GDS remap: passed
- pin label/shape postprocess: passed
- Magic DRC: passed with `DRC_COUNT=0`
- Magic extraction and PEX summary: passed
- PEX capacitor count: `103`
- total listed parasitic capacitance: `865.01 fF`
- output node `vout` capacitance estimate: `363.423 fF`
- connectivity LVS: failed

Current LVS blockers after the environment fix:

- `cfmom_2t` proxy capacitors are present in the source connectivity netlist but do not have matching extracted elements.
- `gnda` is present in the source top ports but is missing from the extracted top port list.
- Source/extracted device and net counts still differ after connectivity normalization.

This means the old Magic/PDK compatibility problem is fixed, and DRC/PEX can now run. The remaining blocker is a real adapter/layout/LVS problem, so the proxy remains non-final.

Local artifacts:

- `generated/analoggym_adapter_audits/amp_dfcfc2/bounded_topk_rank1/amp_dfcfc2_rank1_mim_proxy_magical.sp`
- `generated/analoggym_adapter_audits/amp_dfcfc2/bounded_topk_rank1/conversion_mim_proxy_report.json`
- `generated/analoggym_adapter_audits/amp_dfcfc2/bounded_topk_rank1/adapter_harness_decision_mim_proxy.json`
- `generated/analoggym_adapter_audits/amp_dfcfc2/mim_proxy_magical_smoke/magical_route_log_report.json`
- `generated/analoggym_adapter_audits/amp_dfcfc2/mim_proxy_full_pipeline_fixed_env/summary.md`
- `generated/analoggym_adapter_audits/amp_dfcfc2/mim_proxy_full_pipeline_fixed_env/pex_summary.md`
- `generated/analoggym_adapter_audits/amp_dfcfc2/mim_proxy_full_pipeline_fixed_env/parasitic_summary.json`
- `generated/analoggym_adapter_audits/amp_dfcfc2/mim_proxy_full_pipeline_fixed_env/lvs_result_summary.md`
- `generated/analoggym_adapter_audits/amp_dfcfc2/mim_proxy_full_pipeline_fixed_env/harness_decision.json`

These files are generated artifacts and are intentionally not committed.
