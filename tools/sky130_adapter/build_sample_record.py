#!/usr/bin/env python3
"""Build a graph-learning sample record for a Sky130 MAGICAL case."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build sample_record.json for a Sky130 case.")
    parser.add_argument("--case-name", required=True)
    parser.add_argument("--top-cell", required=True)
    parser.add_argument("--vdd", required=True)
    parser.add_argument("--vss", required=True)
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--source-netlist", type=Path, required=True)
    parser.add_argument("--final-gds", type=Path, required=True)
    parser.add_argument("--raw-extracted-netlist", type=Path, required=True)
    parser.add_argument("--circuit-graph", type=Path, required=True)
    parser.add_argument("--parasitic-summary", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    return parser.parse_args()


def rel_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


def parse_summary_table(summary: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not summary.is_file():
        return values
    row = re.compile(r"^\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|")
    for line in summary.read_text(encoding="utf-8", errors="replace").splitlines():
        match = row.match(line)
        if not match:
            continue
        key = match.group(1).strip()
        value = match.group(2).strip()
        if key not in {"Field", "---"}:
            values[key] = value
    return values


def parse_drc_count(value: str | None) -> int | str:
    if value is None or value == "unknown":
        return "unknown"
    try:
        return int(value)
    except ValueError:
        return value


def parse_pex_total_ff(value: str | None, parasitic_data: dict[str, Any]) -> float | str:
    if "total_cap_ff" in parasitic_data:
        return float(parasitic_data["total_cap_ff"])
    if not value or value == "unknown":
        return "unknown"
    match = re.match(r"([0-9.+\-eE]+)", value)
    return float(match.group(1)) if match else value


def build_sample_record(
    case_name: str,
    top_cell: str,
    vdd: str,
    vss: str,
    case_dir: Path,
    out_dir: Path,
    source_netlist: Path,
    final_gds: Path,
    raw_extracted_netlist: Path,
    circuit_graph: Path,
    parasitic_summary: Path,
    summary: Path,
    repo_root: Path,
) -> dict[str, Any]:
    summary_values = parse_summary_table(summary)
    parasitic_data: dict[str, Any] = {}
    if parasitic_summary.is_file():
        parasitic_data = json.loads(parasitic_summary.read_text(encoding="utf-8"))

    dsc_count = parse_drc_count(summary_values.get("DRC_COUNT"))
    lvs_match = summary_values.get("CONNECTIVITY_LVS_MATCH") == "yes"
    pex_caps = parasitic_data.get("capacitor_count", summary_values.get("PEX_CAPS", "unknown"))
    if isinstance(pex_caps, str) and pex_caps.isdigit():
        pex_caps = int(pex_caps)
    pex_total = parse_pex_total_ff(summary_values.get("PEX_TOTAL_CAP_FF"), parasitic_data)

    graph_exists = circuit_graph.is_file()
    pex_exists = parasitic_summary.is_file()
    drc_clean = dsc_count == 0
    usable = bool(graph_exists and pex_exists and drc_clean and lvs_match and isinstance(pex_caps, int) and pex_caps >= 0)

    return {
        "schema_version": "pex_graph_sample.v1",
        "case_name": case_name,
        "top_cell": top_cell,
        "nets": {
            "vdd": vdd,
            "vss": vss,
        },
        "status": {
            "drc_count": dsc_count,
            "connectivity_lvs_match": lvs_match,
            "pex_capacitor_count": pex_caps,
            "pex_total_cap_ff": pex_total,
        },
        "artifacts": {
            "case_dir": rel_path(case_dir, repo_root),
            "out_dir": rel_path(out_dir, repo_root),
            "source_netlist": rel_path(source_netlist, repo_root),
            "final_gds": rel_path(final_gds, repo_root),
            "raw_extracted_netlist": rel_path(raw_extracted_netlist, repo_root),
            "circuit_graph": rel_path(circuit_graph, repo_root),
            "parasitic_summary": rel_path(parasitic_summary, repo_root),
            "summary": rel_path(summary, repo_root),
        },
        "training_sample": {
            "usable_for_graph_learning": usable,
            "reason": "graph_and_true_magic_pex_available" if usable else "missing_or_unverified_pipeline_artifact",
            "input_graph": rel_path(circuit_graph, repo_root),
            "pex_label": rel_path(parasitic_summary, repo_root),
        },
    }


def main() -> int:
    args = parse_args()
    record = build_sample_record(
        case_name=args.case_name,
        top_cell=args.top_cell,
        vdd=args.vdd,
        vss=args.vss,
        case_dir=args.case_dir,
        out_dir=args.out_dir,
        source_netlist=args.source_netlist,
        final_gds=args.final_gds,
        raw_extracted_netlist=args.raw_extracted_netlist,
        circuit_graph=args.circuit_graph,
        parasitic_summary=args.parasitic_summary,
        summary=args.summary,
        repo_root=args.repo_root,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
