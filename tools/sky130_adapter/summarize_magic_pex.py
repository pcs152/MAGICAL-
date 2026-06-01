#!/usr/bin/env python3
"""Summarize parasitic capacitors in a Magic raw extracted SPICE netlist."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


UNIT_TO_FARADS = {
    "f": 1e-15,
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "m": 1e-3,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize Magic extracted parasitic caps.")
    parser.add_argument("--input", type=Path, required=True, help="Raw extracted SPICE netlist.")
    parser.add_argument("--output", type=Path, required=True, help="Markdown summary path.")
    parser.add_argument("--json-output", type=Path, help="Optional parasitic_summary.json path.")
    parser.add_argument("--top", type=int, default=10, help="Number of largest caps to list.")
    parser.add_argument("--output-node", help="Optional top output node for a focused capacitance estimate.")
    parser.add_argument("--case-name", help="Optional case name for JSON output.")
    parser.add_argument("--top-cell", help="Optional top cell name for JSON output.")
    parser.add_argument(
        "--net-role",
        action="append",
        default=[],
        metavar="NET=ROLE",
        help="Annotate a net role for JSON output. May be repeated.",
    )
    return parser.parse_args()


def parse_cap_value(value: str) -> float | None:
    match = re.fullmatch(r"([0-9.+\-eE]+)([fpnum]?)", value.strip())
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2)
    return number * UNIT_TO_FARADS.get(unit, 1.0)


def fmt_ff(farads: float) -> str:
    return f"{farads / 1e-15:.6g} fF"


def parse_caps(lines: list[str]) -> list[tuple[str, str, str, float]]:
    caps: list[tuple[str, str, str, float]] = []
    for line in lines:
        stripped = line.strip()
        if not re.match(r"^[Cc]\S+\s+", stripped):
            continue
        tokens = stripped.split()
        if len(tokens) < 4:
            continue
        value = parse_cap_value(tokens[3])
        if value is None:
            continue
        name, node1, node2 = tokens[:3]
        caps.append((name, node1, node2, value))
    return caps


def node_stats(caps: list[tuple[str, str, str, float]]) -> tuple[Counter[str], dict[str, float]]:
    per_node_count: Counter[str] = Counter()
    per_node_cap: dict[str, float] = defaultdict(float)
    for _, node1, node2, value in caps:
        for node in (node1, node2):
            per_node_count[node] += 1
            per_node_cap[node] += value
    return per_node_count, per_node_cap


def parse_net_roles(role_args: list[str]) -> dict[str, str]:
    roles: dict[str, str] = {}
    for role_arg in role_args:
        if "=" not in role_arg:
            raise ValueError(f"invalid --net-role value, expected NET=ROLE: {role_arg}")
        net, role = role_arg.split("=", 1)
        net = net.strip()
        role = role.strip()
        if not net or not role:
            raise ValueError(f"invalid --net-role value, expected NET=ROLE: {role_arg}")
        roles[net] = role
    return roles


def ff_value(farads: float) -> float:
    return farads / 1e-15


def net_rank(per_node_cap: dict[str, float], net: str) -> int | None:
    ranked_nets = [name for name, _ in sorted(per_node_cap.items(), key=lambda item: item[1], reverse=True)]
    if net not in ranked_nets:
        return None
    return ranked_nets.index(net) + 1


def build_rule_hits(
    per_node_cap: dict[str, float],
    per_node_count: Counter[str],
    net_roles: dict[str, str],
    output_node: str | None = None,
) -> list[dict[str, Any]]:
    rule_hits: list[dict[str, Any]] = []
    if output_node and output_node in per_node_cap:
        rank = net_rank(per_node_cap, output_node)
        rule_hits.append(
            {
                "rule_id": "output_node_cap_rank",
                "severity": "observation",
                "net": output_node,
                "net_role": net_roles.get(output_node, "output"),
                "cap_rank": rank,
                "capacitor_count": per_node_count[output_node],
                "total_cap_ff": ff_value(per_node_cap[output_node]),
                "meaning": "Output-node parasitic capacitance should be compared with post-layout bandwidth, slew, and load-driving degradation.",
                "suggested_action": "review_backend_then_frontend",
            }
        )

    diff_plus = next((net for net, role in net_roles.items() if role == "differential_input_plus"), None)
    diff_minus = next((net for net, role in net_roles.items() if role == "differential_input_minus"), None)
    if diff_plus and diff_minus and diff_plus in per_node_cap and diff_minus in per_node_cap:
        plus_cap = ff_value(per_node_cap[diff_plus])
        minus_cap = ff_value(per_node_cap[diff_minus])
        denominator = max(plus_cap, minus_cap, 1e-30)
        mismatch_ratio = abs(plus_cap - minus_cap) / denominator
        severity = "warning" if mismatch_ratio > 0.1 else "observation"
        rule_hits.append(
            {
                "rule_id": "differential_input_cap_mismatch",
                "severity": severity,
                "net_plus": diff_plus,
                "net_minus": diff_minus,
                "cap_plus_ff": plus_cap,
                "cap_minus_ff": minus_cap,
                "mismatch_ratio": mismatch_ratio,
                "meaning": "Differential input parasitic imbalance can indicate layout asymmetry and possible offset or CMRR risk.",
                "suggested_action": "review_matching_constraints" if severity == "warning" else "record_as_balanced_example",
            }
        )
    return rule_hits


def build_json_summary(
    caps: list[tuple[str, str, str, float]],
    input_name: str,
    case_name: str | None = None,
    top_cell: str | None = None,
    top: int = 10,
    output_node: str | None = None,
    net_roles: dict[str, str] | None = None,
) -> dict[str, Any]:
    per_node_count, per_node_cap = node_stats(caps)
    total = sum(cap[-1] for cap in caps)
    largest = sorted(caps, key=lambda item: item[-1], reverse=True)[:top]
    roles = dict(net_roles or {})
    if output_node:
        roles.setdefault(output_node, "output")

    return {
        "schema_version": "parasitic_summary.v1",
        "case_name": case_name,
        "top_cell": top_cell,
        "raw_extracted_netlist": input_name,
        "capacitor_count": len(caps),
        "total_cap_ff": ff_value(total),
        "cap_by_net": {
            node: {
                "capacitor_count": per_node_count[node],
                "total_cap_ff": ff_value(value),
                "cap_rank": rank,
                "role": roles.get(node, "unknown"),
            }
            for rank, (node, value) in enumerate(
                sorted(per_node_cap.items(), key=lambda item: item[1], reverse=True),
                start=1,
            )
        },
        "top_caps": [
            {
                "name": name,
                "node1": node1,
                "node2": node2,
                "value_ff": ff_value(value),
            }
            for name, node1, node2, value in largest
        ],
        "net_roles": roles,
        "rule_hits": build_rule_hits(per_node_cap, per_node_count, roles, output_node=output_node),
    }


def render_summary(
    caps: list[tuple[str, str, str, float]],
    input_name: str,
    top: int = 10,
    output_node: str | None = None,
) -> str:
    per_node_count, per_node_cap = node_stats(caps)
    total = sum(cap[-1] for cap in caps)
    largest = sorted(caps, key=lambda item: item[-1], reverse=True)[:top]

    lines = [
        "# Magic PEX Summary",
        "",
        f"- Raw extracted netlist: `{input_name}`",
        f"- Parasitic capacitor count: {len(caps)}",
        f"- Total listed capacitance: {fmt_ff(total)}",
        "",
        "## Per-Node Capacitance",
        "",
        "| Node | Capacitor count | Sum connected capacitance |",
        "| --- | --- | --- |",
    ]
    for node, value in sorted(per_node_cap.items(), key=lambda item: item[1], reverse=True):
        lines.append(f"| `{node}` | {per_node_count[node]} | {fmt_ff(value)} |")

    if output_node:
        lines.extend(
            [
                "",
                "## Output Node Estimate",
                "",
                "| Node | Connected capacitor count | Sum connected capacitance |",
                "| --- | ---: | ---: |",
                f"| `{output_node}` | {per_node_count.get(output_node, 0)} | {fmt_ff(per_node_cap.get(output_node, 0.0))} |",
            ]
        )

    lines.extend(["", f"## Largest {len(largest)} Capacitors", "", "| Cap | Node 1 | Node 2 | Value |", "| --- | --- | --- | --- |"])
    for name, node1, node2, value in largest:
        lines.append(f"| `{name}` | `{node1}` | `{node2}` | {fmt_ff(value)} |")

    lines.extend(
        [
            "",
            "## Note",
            "",
            "This is a PEX summary only. The connectivity LVS netlists intentionally remove",
            "these capacitors, while the raw extracted netlist keeps them for later analysis.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    caps = parse_caps(args.input.read_text(encoding="utf-8", errors="replace").splitlines())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        render_summary(caps, str(args.input), top=args.top, output_node=args.output_node),
        encoding="utf-8",
    )
    if args.json_output:
        net_roles = parse_net_roles(args.net_role)
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(
                build_json_summary(
                    caps,
                    str(args.input),
                    case_name=args.case_name,
                    top_cell=args.top_cell,
                    top=args.top,
                    output_node=args.output_node,
                    net_roles=net_roles,
                ),
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    total = sum(cap[-1] for cap in caps)
    print(f"cap_count={len(caps)}")
    print(f"total_cap_ff={total / 1e-15:.6g}")
    print(f"summary={args.output}")
    if args.json_output:
        print(f"json_summary={args.json_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
