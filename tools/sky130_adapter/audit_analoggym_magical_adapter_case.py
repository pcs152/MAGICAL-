#!/usr/bin/env python3
"""Audit whether an AnalogGym SPICE case is ready for the MAGICAL Sky130 flow."""

from __future__ import annotations

import argparse
import ast
import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SUPPORTED_MAGICAL_MODELS = {
    "sky130_fd_pr__nfet_01v8": "mos",
    "sky130_fd_pr__pfet_01v8": "mos",
}

KNOWN_UNMAPPED_MODELS = {
    "sky130_fd_pr__cap_mim_m3_1": "mim_capacitor",
}


@dataclass(frozen=True)
class Instance:
    name: str
    pins: list[str]
    model: str
    params: dict[str, str]

    @property
    def device_class(self) -> str:
        lower = self.model.lower()
        if "nfet" in lower:
            return "nfet"
        if "pfet" in lower:
            return "pfet"
        if "cap" in lower:
            return "capacitor"
        return "unknown"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit AnalogGym-to-MAGICAL adapter readiness.")
    parser.add_argument("--case-name", required=True)
    parser.add_argument("--netlist", type=Path, required=True)
    parser.add_argument("--vars", dest="vars_path", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--md-output", type=Path, required=True)
    return parser.parse_args()


def parse_params(tokens: list[str]) -> dict[str, str]:
    params: dict[str, str] = {}
    for token in tokens:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        params[key.lower()] = value.strip("'\"")
    return params


def parse_netlist(text: str) -> tuple[str, list[str], list[Instance]]:
    subckt_name = ""
    ports: list[str] = []
    instances: list[Instance] = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("*"):
            continue
        lower = line.lower()
        if lower.startswith(".subckt"):
            tokens = line.split()
            subckt_name = tokens[1]
            ports = tokens[2:]
            continue
        if lower.startswith(".ends"):
            break
        if not lower.startswith("x"):
            continue
        tokens = shlex.split(line, posix=False)
        if len(tokens) < 4:
            continue
        model_idx = next((idx for idx, token in enumerate(tokens[1:], start=1) if token.startswith("sky130_fd_pr__")), None)
        if model_idx is None:
            continue
        instances.append(
            Instance(
                name=tokens[0],
                pins=tokens[1:model_idx],
                model=tokens[model_idx],
                params=parse_params(tokens[model_idx + 1 :]),
            )
        )

    if not subckt_name:
        raise ValueError("No .subckt line found")
    return subckt_name, ports, instances


def parse_vars(text: str) -> dict[str, float]:
    values: dict[str, float] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line.lower().startswith(".param") or "=" not in line:
            continue
        _, assignment = line.split(None, 1)
        key, value = assignment.split("=", 1)
        values[key.strip()] = float(value.strip())
    return values


def eval_expr(expr: str, variables: dict[str, float]) -> float:
    tree = ast.parse(expr, mode="eval")

    def walk(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise KeyError(node.id)
            return variables[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = walk(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            left = walk(node.left)
            right = walk(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            return left / right
        raise ValueError(f"unsupported expression: {expr}")

    return walk(tree)


def resolve_param(value: str, variables: dict[str, float]) -> dict[str, Any]:
    try:
        return {"status": "resolved", "value": eval_expr(value, variables)}
    except Exception as exc:  # noqa: BLE001 - audit should report all parse failures.
        return {"status": "unresolved", "expression": value, "reason": str(exc)}


def classify_ports(ports: list[str]) -> dict[str, str]:
    roles: dict[str, str] = {}
    for port in ports:
        upper = port.upper()
        if upper in {"VOUT", "OUT", "Y"}:
            roles[port] = "output"
        elif upper in {"VINP", "VIP", "INP"}:
            roles[port] = "differential_input_plus"
        elif upper in {"VINN", "VINM", "VIM", "INM"}:
            roles[port] = "differential_input_minus"
        elif upper in {"VDDA", "VDD", "VPWR"}:
            roles[port] = "power"
        elif upper in {"GNDA", "GND", "VGND", "VSS"}:
            roles[port] = "ground"
        elif upper in {"IB", "IBIAS"} or "BIAS" in upper:
            roles[port] = "bias"
        else:
            roles[port] = "unknown"
    return roles


def build_audit(case_name: str, netlist_path: Path, vars_path: Path | None, config_path: Path | None) -> dict[str, Any]:
    subckt_name, ports, instances = parse_netlist(netlist_path.read_text(encoding="utf-8", errors="replace"))
    variables = parse_vars(vars_path.read_text(encoding="utf-8", errors="replace")) if vars_path else {}

    model_counts: dict[str, int] = {}
    device_counts: dict[str, int] = {}
    unsupported_models: dict[str, int] = {}
    unresolved_params: list[dict[str, str]] = []
    symbolic_params = 0
    converted_instances: list[dict[str, Any]] = []

    for inst in instances:
        model_counts[inst.model] = model_counts.get(inst.model, 0) + 1
        device_counts[inst.device_class] = device_counts.get(inst.device_class, 0) + 1
        if inst.model not in SUPPORTED_MAGICAL_MODELS:
            unsupported_models[inst.model] = unsupported_models.get(inst.model, 0) + 1

        resolved: dict[str, Any] = {}
        for key, value in inst.params.items():
            if any(ch.isalpha() for ch in value):
                symbolic_params += 1
            result = resolve_param(value, variables)
            resolved[key] = result
            if result["status"] != "resolved":
                unresolved_params.append({"instance": inst.name, "param": key, "expression": value})

        converted_instances.append(
            {
                "name": inst.name,
                "device_class": inst.device_class,
                "pin_count": len(inst.pins),
                "model": inst.model,
                "params": inst.params,
                "resolved_params": resolved,
                "magical_model_supported": inst.model in SUPPORTED_MAGICAL_MODELS,
            }
        )

    blockers: list[dict[str, str]] = []
    if unsupported_models:
        blockers.append(
            {
                "id": "unsupported_device_models",
                "severity": "blocker",
                "detail": "Some device models are not in MAGICAL's current Sky130 model support set.",
            }
        )
    if unresolved_params:
        blockers.append(
            {
                "id": "unresolved_symbolic_parameters",
                "severity": "blocker",
                "detail": "Some W/L/M/nf parameters cannot be resolved from the AnalogGym vars file.",
            }
        )
    if len(instances) > 10:
        blockers.append(
            {
                "id": "large_case_for_first_adapter",
                "severity": "risk",
                "detail": "The case is much larger than inverter_core/ota_core and should first pass a conversion-only smoke test.",
            }
        )

    readiness = "blocked" if any(item["severity"] == "blocker" for item in blockers) else "candidate"
    return {
        "schema_version": "analoggym_magical_adapter_audit.v1",
        "case_name": case_name,
        "source": {
            "netlist": str(netlist_path),
            "vars": str(vars_path) if vars_path else None,
            "config": str(config_path) if config_path else None,
        },
        "top_cell": subckt_name,
        "ports": ports,
        "port_roles": classify_ports(ports),
        "instance_count": len(instances),
        "device_counts": device_counts,
        "model_counts": model_counts,
        "unsupported_models": unsupported_models,
        "known_unmapped_models": {model: KNOWN_UNMAPPED_MODELS[model] for model in unsupported_models if model in KNOWN_UNMAPPED_MODELS},
        "symbolic_param_count": symbolic_params,
        "unresolved_param_count": len(unresolved_params),
        "unresolved_params": unresolved_params,
        "instances": converted_instances,
        "readiness": readiness,
        "blockers": blockers,
        "recommended_next_tasks": recommended_next_tasks(unsupported_models, unresolved_params),
    }


def recommended_next_tasks(unsupported_models: dict[str, int], unresolved_params: list[dict[str, str]]) -> list[str]:
    tasks = [
        "Create an AnalogGym-to-MAGICAL conversion smoke test for the MOS-only subset.",
        "Evaluate W/L/M/nf expressions from AMP_DFCFC2_vars.spice and emit numeric MAGICAL parameters.",
    ]
    if unsupported_models:
        tasks.append("Decide whether to map, approximate, black-box, or temporarily remove unsupported MIM capacitors.")
    if unresolved_params:
        tasks.append("Extend expression resolution until all instance parameters are numeric.")
    tasks.append("Only after conversion smoke passes, add amp_dfcfc2 as an experimental registry case.")
    return tasks


def write_markdown(audit: dict[str, Any], path: Path) -> None:
    lines = [
        "# amp_dfcfc2 AnalogGym-to-MAGICAL Adapter Audit",
        "",
        "## Summary",
        "",
        f"- Case: `{audit['case_name']}`",
        f"- Top cell: `{audit['top_cell']}`",
        f"- Readiness: `{audit['readiness']}`",
        f"- Instances: {audit['instance_count']}",
        f"- Devices: `{json.dumps(audit['device_counts'], ensure_ascii=False)}`",
        f"- Unsupported models: `{json.dumps(audit['unsupported_models'], ensure_ascii=False)}`",
        f"- Unresolved params: {audit['unresolved_param_count']}",
        "",
        "## Ports",
        "",
    ]
    for port, role in audit["port_roles"].items():
        lines.append(f"- `{port}`: {role}")

    lines.extend(["", "## Blockers", ""])
    if audit["blockers"]:
        for blocker in audit["blockers"]:
            lines.append(f"- `{blocker['id']}` ({blocker['severity']}): {blocker['detail']}")
    else:
        lines.append("- None.")

    lines.extend(["", "## Model Counts", ""])
    for model, count in audit["model_counts"].items():
        supported = "supported" if model not in audit["unsupported_models"] else "unsupported"
        lines.append(f"- `{model}`: {count} ({supported})")

    lines.extend(["", "## Recommended Next Tasks", ""])
    for task in audit["recommended_next_tasks"]:
        lines.append(f"- {task}")

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "`amp_dfcfc2` is a useful V2 target, but it is not ready to enter the existing MAGICAL Sky130 pipeline directly. "
            "The MOS devices use supported Sky130 1.8 V model names, and the AnalogGym vars file is enough to resolve the observed symbolic W/L/M expressions. "
            "The main adapter blocker is the MIM capacitor model `sky130_fd_pr__cap_mim_m3_1`, which is not in the current MAGICAL Sky130 support set. "
            "The next safe step is therefore a conversion-only smoke test before adding the case to the main registry.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    audit = build_audit(args.case_name, args.netlist.resolve(), args.vars_path.resolve() if args.vars_path else None, args.config.resolve() if args.config else None)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(audit, args.md_output)
    print(f"case={audit['case_name']}")
    print(f"readiness={audit['readiness']}")
    print(f"instances={audit['instance_count']}")
    print(f"unsupported_models={len(audit['unsupported_models'])}")
    print(f"unresolved_params={audit['unresolved_param_count']}")
    print(f"json={args.json_output}")
    print(f"markdown={args.md_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
