#!/usr/bin/env python3
"""Build a lightweight circuit graph from a MAGICAL-readable netlist."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


PIN_ORDER = ("D", "G", "S", "B")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build circuit_graph.json from a MAGICAL netlist.")
    parser.add_argument("--input", type=Path, required=True, help="MAGICAL-readable netlist.")
    parser.add_argument("--output", type=Path, required=True, help="Output circuit_graph.json path.")
    parser.add_argument("--top-cell", required=True, help="Top subckt/cell name.")
    return parser.parse_args()


def net_role(name: str) -> str:
    upper = name.upper()
    if upper in {"VOUT", "Y", "OUT", "OUTPUT"} or upper.endswith("OUT"):
        return "output"
    if upper in {"VINP", "VIN+", "INP", "VIP"}:
        return "differential_input_plus"
    if upper in {"VINM", "VIN-", "INM", "VIM"}:
        return "differential_input_minus"
    if upper in {"VDD", "VPWR", "VDDA", "VCCA"}:
        return "power"
    if upper in {"GND", "VGND", "VSS", "GNDA", "VSSA"}:
        return "ground"
    if upper in {"IB", "IBIAS", "BIAS"} or "BIAS" in upper or upper.startswith("VB"):
        return "bias"
    return "internal"


def parse_params(text: str) -> dict[str, str]:
    params: dict[str, str] = {}
    for key, value in re.findall(r"(\w+)\s*=\s*('[^']+'|\"[^\"]+\"|\S+)", text):
        params[key] = value.strip("'\"")
    return params


def find_subckt(lines: list[str], top_cell: str) -> tuple[list[str], list[str]]:
    start_re = re.compile(rf"^\s*\.?subckt\s+{re.escape(top_cell)}\b\s*(.*)$", re.IGNORECASE)
    end_re = re.compile(r"^\s*\.?ends\b", re.IGNORECASE)
    ports: list[str] = []
    body: list[str] = []
    inside = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("*"):
            continue
        if not inside:
            match = start_re.match(stripped)
            if not match:
                continue
            ports = match.group(1).split()
            inside = True
            continue
        if end_re.match(stripped):
            break
        body.append(stripped)
    if not ports:
        raise ValueError(f"top subckt not found: {top_cell}")
    return ports, body


def parse_mos_line(line: str) -> dict[str, Any] | None:
    match = re.match(r"^\s*(M\S*)\s*\(([^)]*)\)\s+(\S+)(.*)$", line, flags=re.IGNORECASE)
    if not match:
        return None
    name, pin_text, model, param_text = match.groups()
    pins = pin_text.split()
    if len(pins) != 4:
        raise ValueError(f"MOS instance must have 4 pins: {line}")
    model_lower = model.lower()
    if "nfet" in model_lower:
        device_type = "nfet"
    elif "pfet" in model_lower:
        device_type = "pfet"
    else:
        device_type = "mos"
    return {
        "id": name,
        "node_type": "device",
        "device_class": "mos",
        "device_type": device_type,
        "model": model,
        "pins": dict(zip(PIN_ORDER, pins)),
        "params": parse_params(param_text),
    }


def build_graph_from_text(text: str, top_cell: str) -> dict[str, Any]:
    ports, body = find_subckt(text.splitlines(), top_cell)
    devices: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    nets: set[str] = set(ports)

    for line in body:
        mos = parse_mos_line(line)
        if mos is None:
            continue
        devices.append({key: value for key, value in mos.items() if key != "pins"})
        for pin, net in mos["pins"].items():
            nets.add(net)
            edges.append(
                {
                    "source": mos["id"],
                    "target": net,
                    "pin": pin,
                    "edge_type": "device_net_connection",
                }
            )

    degree = Counter(edge["target"] for edge in edges)
    nodes: list[dict[str, Any]] = []
    nodes.extend(sorted(devices, key=lambda node: node["id"]))
    for net in sorted(nets):
        nodes.append(
            {
                "id": net,
                "node_type": "net",
                "role": net_role(net),
                "is_port": net in ports,
                "degree": degree.get(net, 0),
            }
        )

    return {
        "schema_version": "circuit_graph.v1",
        "top_cell": top_cell,
        "ports": ports,
        "nodes": nodes,
        "edges": edges,
        "metadata": {
            "device_count": len(devices),
            "net_count": len(nets),
            "edge_count": len(edges),
            "supported_syntax": "magical_mos_v1",
        },
    }


def main() -> int:
    args = parse_args()
    graph = build_graph_from_text(args.input.read_text(encoding="utf-8", errors="replace"), args.top_cell)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
