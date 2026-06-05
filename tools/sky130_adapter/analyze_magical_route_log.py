#!/usr/bin/env python3
"""Analyze MAGICAL placement/routing logs for Harness decisions."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


FAILED_ROUTE_RE = re.compile(r"Route net\s+([^\s,]+)\s+failed!", re.IGNORECASE)
UNROUTED_RE = re.compile(r"Unrouted nets\s+\d+\s*,\s*(.*)$", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze a MAGICAL routing log.")
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case-name", default="")
    parser.add_argument("--top-cell", default="")
    return parser.parse_args()


def unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def parse_unrouted_nets(raw: str) -> list[str]:
    cleaned = raw.strip()
    if not cleaned:
        return []
    if cleaned.startswith("Parsing "):
        return []
    nets: list[str] = []
    for item in cleaned.split():
        token = item.strip().strip(",")
        if not token:
            continue
        if token in {"Parsing", "LEF", "Tech", "file"} or token.endswith(".lef") or token.endswith(".techfile"):
            continue
        nets.append(token)
    return nets


def analyze_route_log(text: str, log_path: Path, case_name: str = "", top_cell: str = "") -> dict[str, Any]:
    failed_route_nets: list[str] = []
    unrouted_iterations: list[dict[str, Any]] = []
    route_gds_written = False
    routing_finished = False

    for line_no, line in enumerate(text.splitlines(), start=1):
        failed_match = FAILED_ROUTE_RE.search(line)
        if failed_match:
            failed_route_nets.append(failed_match.group(1))

        unrouted_match = UNROUTED_RE.search(line)
        if unrouted_match:
            nets = parse_unrouted_nets(unrouted_match.group(1))
            unrouted_iterations.append({"line": line_no, "nets": nets})

        if "Writing Routing GDS Layout" in line:
            route_gds_written = True
        if "PnR: routing finished" in line:
            routing_finished = True

    failed_route_nets = unique(failed_route_nets)
    last_unrouted_nets = unrouted_iterations[-1]["nets"] if unrouted_iterations else []
    has_route_warnings = bool(failed_route_nets or last_unrouted_nets)
    completed = route_gds_written and routing_finished
    if completed and has_route_warnings:
        status = "completed_with_route_warnings"
    elif completed:
        status = "completed_clean"
    else:
        status = "incomplete"

    return {
        "schema_version": "magical_route_log_report.v1",
        "case_name": case_name,
        "top_cell": top_cell,
        "log": str(log_path),
        "status": status,
        "route_gds_written": route_gds_written,
        "routing_finished": routing_finished,
        "failed_route_nets": failed_route_nets,
        "last_unrouted_nets": last_unrouted_nets,
        "unrouted_iterations": unrouted_iterations,
        "smoke_allowed": completed,
        "final_flow_allowed": completed and not has_route_warnings,
        "meaning": (
            "MAGICAL wrote a route GDS, but the route log still contains failed or unresolved nets. "
            "Treat this as a smoke result that requires layout/routing review before final flow."
            if completed and has_route_warnings
            else "MAGICAL routing log does not contain detected failed or unresolved route nets."
            if completed
            else "MAGICAL routing did not reach a complete route GDS output."
        ),
    }


def main() -> int:
    args = parse_args()
    report = analyze_route_log(
        args.log.read_text(encoding="utf-8", errors="replace"),
        args.log.resolve(),
        args.case_name,
        args.top_cell,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"status={report['status']}")
    print(f"route_gds_written={str(report['route_gds_written']).lower()}")
    print(f"failed_route_nets={','.join(report['failed_route_nets']) or 'none'}")
    print(f"last_unrouted_nets={','.join(report['last_unrouted_nets']) or 'none'}")
    print(f"final_flow_allowed={str(report['final_flow_allowed']).lower()}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
