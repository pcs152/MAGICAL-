#!/usr/bin/env python3
"""Build a V1 rule-based parasitic risk report from graph and Magic PEX summaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SEVERITY_ORDER = {"observation": 0, "warning": 1, "fail": 2}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build risk_report.json for a Sky130 PEX graph sample.")
    parser.add_argument("--circuit-graph", type=Path, required=True)
    parser.add_argument("--parasitic-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def graph_net_roles(graph: dict[str, Any]) -> dict[str, str]:
    roles: dict[str, str] = {}
    for node in graph.get("nodes", []):
        if node.get("node_type") == "net":
            roles[str(node["id"])] = str(node.get("role", "unknown"))
    return roles


def graph_net_degrees(graph: dict[str, Any]) -> dict[str, int]:
    degrees: dict[str, int] = {}
    for node in graph.get("nodes", []):
        if node.get("node_type") == "net":
            degrees[str(node["id"])] = int(node.get("degree", 0))
    return degrees


def cap_entry(parasitic: dict[str, Any], net: str) -> dict[str, Any] | None:
    entry = parasitic.get("cap_by_net", {}).get(net)
    return entry if isinstance(entry, dict) else None


def ff(entry: dict[str, Any]) -> float:
    return float(entry.get("total_cap_ff", 0.0))


def severity_max(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "observation"
    return max((str(item.get("severity", "observation")) for item in findings), key=lambda s: SEVERITY_ORDER.get(s, 0))


def append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def build_risk_report(graph: dict[str, Any], parasitic: dict[str, Any]) -> dict[str, Any]:
    roles = graph_net_roles(graph)
    degrees = graph_net_degrees(graph)
    cap_by_net: dict[str, Any] = parasitic.get("cap_by_net", {})
    total_cap_ff = float(parasitic.get("total_cap_ff", 0.0) or 0.0)
    findings: list[dict[str, Any]] = []

    for net, role in roles.items():
        entry = cap_entry(parasitic, net)
        if entry is None:
            continue
        cap_ff = ff(entry)
        share = cap_ff / total_cap_ff if total_cap_ff > 0 else 0.0

        if role == "output":
            severity = "warning" if share >= 0.15 or int(entry.get("cap_rank", 999)) <= 3 else "observation"
            findings.append(
                {
                    "rule_id": "output_node_cap",
                    "severity": severity,
                    "net": net,
                    "net_role": role,
                    "total_cap_ff": cap_ff,
                    "total_cap_share": share,
                    "cap_rank": entry.get("cap_rank"),
                    "meaning": "输出节点寄生电容会直接影响带宽、转换速度、负载驱动和相位裕度。",
                    "suggested_action": "review_backend_layout" if severity == "warning" else "record_as_training_sample",
                }
            )
        elif role == "bias":
            severity = "warning" if share >= 0.10 else "observation"
            findings.append(
                {
                    "rule_id": "bias_node_cap",
                    "severity": severity,
                    "net": net,
                    "net_role": role,
                    "total_cap_ff": cap_ff,
                    "total_cap_share": share,
                    "cap_rank": entry.get("cap_rank"),
                    "meaning": "偏置节点寄生电容可能影响工作点建立、偏置稳定性和启动速度。",
                    "suggested_action": "review_bias_route" if severity == "warning" else "record_as_training_sample",
                }
            )

    diff_plus = next((net for net, role in roles.items() if role == "differential_input_plus"), None)
    diff_minus = next((net for net, role in roles.items() if role == "differential_input_minus"), None)
    plus_entry = cap_entry(parasitic, diff_plus) if diff_plus else None
    minus_entry = cap_entry(parasitic, diff_minus) if diff_minus else None
    if diff_plus and diff_minus and plus_entry and minus_entry:
        plus_cap = ff(plus_entry)
        minus_cap = ff(minus_entry)
        mismatch = abs(plus_cap - minus_cap) / max(plus_cap, minus_cap, 1e-30)
        severity = "warning" if mismatch >= 0.10 else "observation"
        findings.append(
            {
                "rule_id": "differential_input_cap_mismatch",
                "severity": severity,
                "net_plus": diff_plus,
                "net_minus": diff_minus,
                "cap_plus_ff": plus_cap,
                "cap_minus_ff": minus_cap,
                "mismatch_ratio": mismatch,
                "meaning": "差分输入两侧寄生不平衡可能对应失配、输入等效偏移或共模抑制变差风险。",
                "suggested_action": "review_matching_constraints" if severity == "warning" else "record_as_balanced_example",
            }
        )

    known_nets = set(roles)
    for net, entry in cap_by_net.items():
        if net in known_nets:
            continue
        cap_ff = ff(entry)
        share = cap_ff / total_cap_ff if total_cap_ff > 0 else 0.0
        if share < 0.12:
            continue
        findings.append(
            {
                "rule_id": "large_unmapped_extracted_net",
                "severity": "warning",
                "net": net,
                "net_role": "extracted_internal_or_unmapped",
                "total_cap_ff": cap_ff,
                "total_cap_share": share,
                "cap_rank": entry.get("cap_rank"),
                "meaning": "Magic 提取出的未映射内部网络占比较大，说明版图内部节点可能存在较重寄生，需要回看布局布线或后续建立映射关系。",
                "suggested_action": "review_backend_layout",
            }
        )

    actions: list[str] = []
    for finding in findings:
        append_unique(actions, str(finding.get("suggested_action", "manual_review")))
    append_unique(actions, "record_as_training_sample")

    return {
        "schema_version": "parasitic_risk_report.v1",
        "case_name": parasitic.get("case_name"),
        "top_cell": parasitic.get("top_cell") or graph.get("top_cell"),
        "summary": {
            "max_severity": severity_max(findings),
            "finding_count": len(findings),
            "total_cap_ff": total_cap_ff,
            "recommended_actions": actions,
        },
        "net_context": {
            net: {"role": role, "degree": degrees.get(net, 0)}
            for net, role in sorted(roles.items())
        },
        "findings": findings,
    }


def main() -> int:
    args = parse_args()
    graph = json.loads(args.circuit_graph.read_text(encoding="utf-8"))
    parasitic = json.loads(args.parasitic_summary.read_text(encoding="utf-8"))
    report = build_risk_report(graph, parasitic)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
