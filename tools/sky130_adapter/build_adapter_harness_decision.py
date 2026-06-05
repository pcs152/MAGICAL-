#!/usr/bin/env python3
"""Build a Harness decision for AnalogGym-to-MAGICAL adapter conversion reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


KNOWN_MODEL_CATEGORIES = {
    "sky130_fd_pr__cap_mim_m3_1": "mim_capacitor",
}

MIM_CAP_ACTIONS = [
    "add_mim_cap_mapping",
    "use_black_box_macro",
    "block_final_pipeline_until_supported",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build adapter_harness_decision.json from a conversion report.")
    parser.add_argument("--conversion-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def model_category(model: str, device_class: str) -> str:
    if model in KNOWN_MODEL_CATEGORIES:
        return KNOWN_MODEL_CATEGORIES[model]
    if "cap" in model.lower() or device_class == "capacitor":
        return "unknown_capacitor"
    return "unknown_device"


def issue_from_instance(instance: dict[str, Any], source: str) -> dict[str, Any]:
    model = str(instance.get("model", "unknown"))
    device_class = str(instance.get("device_class", "unknown"))
    category = model_category(model, device_class)
    allowed_for_smoke = category == "mim_capacitor"
    recommended_actions = MIM_CAP_ACTIONS if category == "mim_capacitor" else ["add_model_mapping"]
    return {
        "issue_type": "unsupported_device_model",
        "source": source,
        "name": instance.get("name"),
        "model": model,
        "device_class": device_class,
        "known_category": category,
        "severity": "blocker",
        "allowed_for_smoke": allowed_for_smoke,
        "allowed_for_final_flow": False,
        "recommended_actions": recommended_actions,
        "meaning": (
            "MIM 电容是电路真实性能的一部分；省略它只能用于 adapter smoke，"
            "不能作为最终版图或后仿性能证据。"
            if category == "mim_capacitor"
            else "当前 MAGICAL adapter 不支持该器件模型，最终流程必须阻塞。"
        ),
    }


def build_adapter_harness_decision(conversion_report: dict[str, Any]) -> dict[str, Any]:
    unsupported = conversion_report.get("unsupported_instances", [])
    omitted = conversion_report.get("omitted_instances", [])
    issues: list[dict[str, Any]] = []

    if isinstance(unsupported, list):
        issues.extend(issue_from_instance(item, "unsupported_instances") for item in unsupported if isinstance(item, dict))
    if isinstance(omitted, list):
        issues.extend(issue_from_instance(item, "omitted_instances") for item in omitted if isinstance(item, dict))

    if not issues:
        decision = "accept_conversion"
        smoke_allowed = True
        final_flow_allowed = True
        recommended_actions = ["continue_to_pipeline"]
    else:
        final_flow_allowed = all(bool(issue.get("allowed_for_final_flow")) for issue in issues)
        smoke_allowed = all(bool(issue.get("allowed_for_smoke")) for issue in issues)
        if omitted:
            decision = "smoke_only_not_final"
            recommended_actions = ["do_not_use_for_final_performance"]
        else:
            decision = "block_final_flow"
            recommended_actions = []
        for issue in issues:
            recommended_actions.extend(issue.get("recommended_actions", []))

    return {
        "schema_version": "adapter_harness_decision.v1",
        "top_cell": conversion_report.get("top_cell"),
        "conversion_status": conversion_report.get("status"),
        "decision": decision,
        "smoke_allowed": smoke_allowed,
        "final_flow_allowed": final_flow_allowed,
        "issue_count": len(issues),
        "issues": issues,
        "recommended_actions": unique(recommended_actions),
        "inputs": {
            "conversion_report_schema": conversion_report.get("schema_version"),
        },
    }


def main() -> int:
    args = parse_args()
    conversion_report = json.loads(args.conversion_report.read_text(encoding="utf-8"))
    decision = build_adapter_harness_decision(conversion_report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(decision, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"decision={decision['decision']}")
    print(f"smoke_allowed={str(decision['smoke_allowed']).lower()}")
    print(f"final_flow_allowed={str(decision['final_flow_allowed']).lower()}")
    print(f"issue_count={decision['issue_count']}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
