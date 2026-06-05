# Sky130 Environment Diagnosis

## Summary

- Environment status: `pass`
- Suspected issue: `unknown`
- Impact: `environment_ready_or_needs_light_review`

## Tools

- Magic: `8.3.483` at `/home/qlf/IOT/scripts/env/bin/magic`
- Docker: `Docker version 28.4.0, build d8eb465` at `/usr/bin/docker`
- Netgen: `/usr/bin/netgen-lvs`

## PDK

- Expected hash: `7b70722e33c03fcb5dabcf4d479fb0822d9251c9`
- Actual hash: `7b70722e33c03fcb5dabcf4d479fb0822d9251c9`
- SKY130A: `/home/qlf/.ciel/ciel/sky130/versions/7b70722e33c03fcb5dabcf4d479fb0822d9251c9/sky130A`
- PDK_ROOT: `/home/qlf/.ciel/ciel/sky130/versions/7b70722e33c03fcb5dabcf4d479fb0822d9251c9`
- magicrc exists: `True`
- techfile exists: `True`
- netgen setup exists: `True`

## Recent Magic DRC Log

- Log path: `/home/qlf/IOT/references/MAGICAL-/generated/sky130_cases/inverter_core_post_cleanup/magic_drc.log`
- Techfile parse errors: `False`
- Segmentation fault: `False`
- Recent pipeline failed stage: `none`

## Recommended Next Actions

- `rerun_small_case_pipeline`
