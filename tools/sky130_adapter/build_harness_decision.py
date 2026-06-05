#!/usr/bin/env python3
"""Build a V1 Harness decision record from risk report and sample status."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SEVERITY_ORDER = {"observation": 0, "warning": 1, "fail": 2}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build harness_decision.json for a Sky130 case.")
    parser.add_argument("--risk-report", type=Path, required=True)
    parser.add_argument("--sample-record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def build_harness_decision(risk_report: dict[str, Any], sample_record: dict[str, Any]) -> dict[str, Any]:
    sample_status = sample_record.get("status", {})
    graph_usable = bool(sample_record.get("training_sample", {}).get("usable_for_graph_learning", False))
    lvs_ok = sample_status.get("connectivity_lvs_match") is True
    drc_ok = sample_status.get("drc_count") == 0
    pex_caps = sample_status.get("pex_capacitor_count")
    pex_ok = isinstance(pex_caps, int) and pex_caps >= 0

    recommended_actions: list[str] = []
    blocking_reasons: list[str] = []
    if not drc_ok:
        blocking_reasons.append("drc_not_clean")
    if not lvs_ok:
        blocking_reasons.append("lvs_not_matched")
    if not pex_ok:
        blocking_reasons.append("pex_missing_or_invalid")
    if not graph_usable:
        blocking_reasons.append("sample_not_marked_usable")

    if blocking_reasons:
        decision = "reject_pipeline_artifact"
        usable_for_training = False
        recommended_actions.append("fix_pipeline_artifact")
    else:
        max_severity = str(risk_report.get("summary", {}).get("max_severity", "observation"))
        if SEVERITY_ORDER.get(max_severity, 0) >= SEVERITY_ORDER["fail"]:
            decision = "reject_candidate"
            usable_for_training = True
            recommended_actions.append("manual_review")
        elif max_severity == "warning":
            decision = "review_with_warnings"
            usable_for_training = True
            recommended_actions.extend(risk_report.get("summary", {}).get("recommended_actions", []))
        else:
            decision = "accept_as_v1_sample"
            usable_for_training = True
            recommended_actions.extend(risk_report.get("summary", {}).get("recommended_actions", []))

    return {
        "schema_version": "harness_decision.v1",
        "case_name": risk_report.get("case_name") or sample_record.get("case_name"),
        "decision": decision,
        "usable_for_training": usable_for_training,
        "blocking_reasons": blocking_reasons,
        "recommended_actions": unique(recommended_actions),
        "inputs": {
            "risk_report_schema": risk_report.get("schema_version"),
            "sample_record_schema": sample_record.get("schema_version"),
        },
    }


def main() -> int:
    args = parse_args()
    risk_report = json.loads(args.risk_report.read_text(encoding="utf-8"))
    sample_record = json.loads(args.sample_record.read_text(encoding="utf-8"))
    decision = build_harness_decision(risk_report, sample_record)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(decision, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
