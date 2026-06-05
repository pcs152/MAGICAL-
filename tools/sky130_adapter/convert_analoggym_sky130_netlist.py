#!/usr/bin/env python3
"""Convert an AnalogGym Sky130 netlist into a MAGICAL-readable netlist."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from audit_analoggym_magical_adapter_case import (
    SUPPORTED_MAGICAL_MODELS,
    Instance,
    parse_netlist,
    parse_vars,
    resolve_param,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert AnalogGym Sky130 SPICE to MAGICAL syntax.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--vars", dest="vars_path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--unsupported-cap-policy",
        choices=("block", "omit-with-report"),
        default="block",
        help="How to handle unsupported MIM capacitors in the first adapter smoke path.",
    )
    return parser.parse_args()


def format_um(value: float) -> str:
    if value < 1.0:
        return f"{value * 1000:g}n"
    return f"{value:g}u"


def format_int(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:g}"


def resolve_required_float(inst: Instance, key: str, variables: dict[str, float]) -> float:
    if key not in inst.params:
        raise ValueError(f"{inst.name} missing required parameter {key}")
    result = resolve_param(inst.params[key], variables)
    if result["status"] != "resolved":
        raise ValueError(f"{inst.name} parameter {key} unresolved: {inst.params[key]}")
    return float(result["value"])


def convert_mos_instance(inst: Instance, variables: dict[str, float]) -> str:
    if len(inst.pins) != 4:
        raise ValueError(f"{inst.name} MOS instance must have 4 pins")
    length = resolve_required_float(inst, "l", variables)
    width = resolve_required_float(inst, "w", variables)
    nf = resolve_required_float(inst, "nf", variables)
    multi_key = "multi" if "multi" in inst.params else "m"
    multi = resolve_required_float(inst, multi_key, variables)
    name = inst.name[1:] if inst.name.upper().startswith("XM") else inst.name
    return (
        f"{name} ({' '.join(inst.pins)}) {inst.model} "
        f"l={format_um(length)} w={format_um(width)} multi={format_int(multi)} nf={format_int(nf)}"
    )


def build_report(
    input_path: Path,
    output_path: Path,
    subckt_name: str,
    ports: list[str],
    converted: list[dict[str, Any]],
    omitted: list[dict[str, Any]],
    status: str,
) -> dict[str, Any]:
    return {
        "schema_version": "analoggym_magical_conversion_report.v1",
        "status": status,
        "source_netlist": str(input_path),
        "output_netlist": str(output_path),
        "top_cell": subckt_name,
        "ports": ports,
        "converted_instances": converted,
        "omitted_instances": omitted,
    }


def convert(
    input_path: Path,
    vars_path: Path,
    output_path: Path,
    report_path: Path,
    unsupported_cap_policy: str,
) -> dict[str, Any]:
    subckt_name, ports, instances = parse_netlist(input_path.read_text(encoding="utf-8", errors="replace"))
    variables = parse_vars(vars_path.read_text(encoding="utf-8", errors="replace"))
    converted: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []
    output_lines = [f"subckt {subckt_name} {' '.join(ports)}"]

    unsupported = [inst for inst in instances if inst.model not in SUPPORTED_MAGICAL_MODELS]
    if unsupported and unsupported_cap_policy == "block":
        report = build_report(input_path, output_path, subckt_name, ports, converted, [], "blocked")
        report["unsupported_instances"] = [
            {"name": inst.name, "model": inst.model, "device_class": inst.device_class} for inst in unsupported
        ]
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        models = ", ".join(sorted({inst.model for inst in unsupported}))
        raise SystemExit(f"unsupported AnalogGym devices for MAGICAL conversion: {models}")

    for inst in instances:
        if inst.model in SUPPORTED_MAGICAL_MODELS:
            line = convert_mos_instance(inst, variables)
            output_lines.append(line)
            converted.append({"name": inst.name, "model": inst.model, "output": line})
            continue
        omitted.append({"name": inst.name, "model": inst.model, "device_class": inst.device_class, "reason": "unsupported_model"})

    output_lines.append(f"ends {subckt_name}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")

    report = build_report(input_path, output_path, subckt_name, ports, converted, omitted, "converted")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    args = parse_args()
    report = convert(
        args.input.resolve(),
        args.vars_path.resolve(),
        args.output.resolve(),
        args.report.resolve(),
        args.unsupported_cap_policy,
    )
    print(f"status={report['status']}")
    print(f"converted_instances={len(report['converted_instances'])}")
    print(f"omitted_instances={len(report['omitted_instances'])}")
    print(f"output={args.output}")
    print(f"report={args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
