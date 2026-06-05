#!/usr/bin/env python3
"""Diagnose the local Sky130/MAGICAL tool environment."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HASH = "7b70722e33c03fcb5dabcf4d479fb0822d9251c9"
DEFAULT_SKY130A = Path.home() / ".ciel/ciel/sky130/versions" / DEFAULT_HASH / "sky130A"
DEFAULT_JSON_OUTPUT = REPO_ROOT / "generated/sky130_environment_diagnosis.json"
DEFAULT_MD_OUTPUT = REPO_ROOT / "docs/sky130_adapter/sky130_environment_diagnosis.md"
DEFAULT_DRC_LOG = REPO_ROOT / "generated/sky130_cases/inverter_core_post_cleanup/magic_drc.log"
DEFAULT_SUMMARY = REPO_ROOT / "generated/sky130_cases/inverter_core_post_cleanup/summary.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose local Sky130/MAGICAL environment.")
    parser.add_argument("--sky130a", type=Path, default=Path(os.environ.get("SKY130A", DEFAULT_SKY130A)))
    parser.add_argument("--pdk-root", type=Path, default=None)
    parser.add_argument("--recent-magic-drc-log", type=Path, default=DEFAULT_DRC_LOG)
    parser.add_argument("--recent-summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def command_output(command: list[str]) -> str:
    try:
        result = subprocess.run(command, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except OSError as exc:
        return f"unavailable: {exc}"
    return result.stdout.strip()


def first_line(text: str) -> str:
    return text.splitlines()[0].strip() if text.strip() else "unknown"


def pdk_hash_from_sky130a(sky130a: Path) -> str:
    parts = sky130a.resolve().parts
    if "versions" not in parts:
        return "unknown"
    index = parts.index("versions")
    if index + 1 >= len(parts):
        return "unknown"
    return parts[index + 1]


def analyze_magic_drc_log(text: str) -> dict[str, Any]:
    lowered = text.lower()
    has_defaultsidewall = "defaultsidewall" in lowered and "malformed line" in lowered
    has_device_error = "malformed line for keyword device" in lowered
    has_a1_error = "unrecognized layer (type) name" in lowered and "a1>" in lowered
    has_techfile_parse_errors = has_defaultsidewall or has_device_error or has_a1_error
    has_segmentation_fault = "segmentation fault" in lowered or "segfault" in lowered
    suspected_issue = "unknown"
    if has_techfile_parse_errors and has_segmentation_fault:
        suspected_issue = "magic_pdk_incompatibility"
    elif has_techfile_parse_errors:
        suspected_issue = "pdk_techfile_parse_errors"
    elif has_segmentation_fault:
        suspected_issue = "magic_crash"

    return {
        "has_techfile_parse_errors": has_techfile_parse_errors,
        "has_segmentation_fault": has_segmentation_fault,
        "has_defaultsidewall_errors": has_defaultsidewall,
        "has_device_errors": has_device_error,
        "has_a1_layer_errors": has_a1_error,
        "suspected_issue": suspected_issue,
    }


def read_log_analysis(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "path": str(path),
            "exists": False,
            "has_techfile_parse_errors": False,
            "has_segmentation_fault": False,
            "suspected_issue": "no_recent_log",
        }
    analysis = analyze_magic_drc_log(path.read_text(encoding="utf-8", errors="replace"))
    return {"path": str(path), "exists": True, **analysis}


def read_pipeline_summary(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "exists": False, "failed_stage": "unknown", "status": "unknown"}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "|" not in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0] not in {"Field", "---"}:
            values[cells[0]] = cells[1]
    return {
        "path": str(path),
        "exists": True,
        "status": values.get("STATUS", "unknown"),
        "failed_stage": values.get("FAILED_STAGE", "none"),
        "message": values.get("MESSAGE", ""),
    }


def tool_record(path: str | None, version: str) -> dict[str, str]:
    return {
        "path": path or "missing",
        "version": version or "unknown",
    }


def build_diagnosis(
    sky130a: Path,
    pdk_root: Path,
    magic_version: str,
    magic_path: str | None,
    docker_version: str,
    docker_path: str | None,
    netgen_path: str | None,
    recent_magic_drc_log: Path,
    recent_summary: Path,
) -> dict[str, Any]:
    magicrc = sky130a / "libs.tech/magic/sky130A.magicrc"
    techfile = sky130a / "libs.tech/magic/sky130A.tech"
    netgen_setup = sky130a / "libs.tech/netgen/sky130A_setup.tcl"
    log_analysis = read_log_analysis(recent_magic_drc_log)
    summary_analysis = read_pipeline_summary(recent_summary)
    pdk_hash = pdk_hash_from_sky130a(sky130a)

    missing_required = [
        name
        for name, exists in {
            "magic": bool(magic_path),
            "docker": bool(docker_path),
            "netgen": bool(netgen_path),
            "sky130A": sky130a.is_dir(),
            "sky130A.magicrc": magicrc.is_file(),
            "sky130A.tech": techfile.is_file(),
            "sky130A_setup.tcl": netgen_setup.is_file(),
        }.items()
        if not exists
    ]

    suspected_issue = str(log_analysis.get("suspected_issue", "unknown"))
    failed_at_magic_drc = summary_analysis.get("failed_stage") == "magic_drc"
    if suspected_issue == "pdk_techfile_parse_errors" and failed_at_magic_drc:
        suspected_issue = "magic_pdk_incompatibility"
    status = "pass"
    if missing_required or suspected_issue == "magic_pdk_incompatibility":
        status = "fail"
    elif pdk_hash != DEFAULT_HASH or suspected_issue not in {"unknown", "no_recent_log"}:
        status = "warning"

    actions: list[str] = []
    if missing_required:
        actions.append("install_or_locate_missing_tools")
    if suspected_issue == "magic_pdk_incompatibility":
        actions.append("pin_compatible_magic_pdk_combo")
        actions.append("ask_senior_for_known_good_environment")
    if pdk_hash != DEFAULT_HASH:
        actions.append("align_pdk_hash_with_project_default")
    if not actions:
        actions.append("rerun_small_case_pipeline")

    impact = "full_pipeline_blocked_but_v1_incremental_available" if status == "fail" else "environment_ready_or_needs_light_review"

    return {
        "schema_version": "sky130_environment_diagnosis.v1",
        "environment_status": status,
        "suspected_issue": suspected_issue,
        "tools": {
            "magic": tool_record(magic_path, magic_version),
            "docker": tool_record(docker_path, docker_version),
            "netgen": tool_record(netgen_path, "path_only"),
        },
        "pdk": {
            "expected_hash": DEFAULT_HASH,
            "hash": pdk_hash,
            "sky130a": str(sky130a),
            "pdk_root": str(pdk_root),
            "magicrc_exists": magicrc.is_file(),
            "techfile_exists": techfile.is_file(),
            "netgen_setup_exists": netgen_setup.is_file(),
        },
        "recent_magic_drc_log": log_analysis,
        "recent_pipeline_summary": summary_analysis,
        "missing_required": missing_required,
        "impact": impact,
        "recommended_next_actions": actions,
    }


def collect_current_diagnosis(args: argparse.Namespace) -> dict[str, Any]:
    sky130a = args.sky130a.expanduser().resolve()
    pdk_root = args.pdk_root.expanduser().resolve() if args.pdk_root else sky130a.parent
    return build_diagnosis(
        sky130a=sky130a,
        pdk_root=pdk_root,
        magic_version=first_line(command_output(["magic", "--version"])),
        magic_path=shutil.which("magic"),
        docker_version=first_line(command_output(["docker", "--version"])),
        docker_path=shutil.which("docker"),
        netgen_path=shutil.which("netgen") or shutil.which("netgen-lvs"),
        recent_magic_drc_log=args.recent_magic_drc_log.expanduser().resolve(),
        recent_summary=args.recent_summary.expanduser().resolve(),
    )


def render_markdown(diagnosis: dict[str, Any]) -> str:
    tools = diagnosis.get("tools", {})
    pdk = diagnosis.get("pdk", {})
    log = diagnosis.get("recent_magic_drc_log", {})
    summary = diagnosis.get("recent_pipeline_summary", {})
    actions = diagnosis.get("recommended_next_actions", [])
    lines = [
        "# Sky130 Environment Diagnosis",
        "",
        "## Summary",
        "",
        f"- Environment status: `{diagnosis.get('environment_status')}`",
        f"- Suspected issue: `{diagnosis.get('suspected_issue')}`",
        f"- Impact: `{diagnosis.get('impact')}`",
        "",
        "## Tools",
        "",
        f"- Magic: `{tools.get('magic', {}).get('version', 'unknown')}` at `{tools.get('magic', {}).get('path', 'missing')}`",
        f"- Docker: `{tools.get('docker', {}).get('version', 'unknown')}` at `{tools.get('docker', {}).get('path', 'missing')}`",
        f"- Netgen: `{tools.get('netgen', {}).get('path', 'missing')}`",
        "",
        "## PDK",
        "",
        f"- Expected hash: `{pdk.get('expected_hash', 'unknown')}`",
        f"- Actual hash: `{pdk.get('hash', 'unknown')}`",
        f"- SKY130A: `{pdk.get('sky130a', 'unknown')}`",
        f"- PDK_ROOT: `{pdk.get('pdk_root', 'unknown')}`",
        f"- magicrc exists: `{pdk.get('magicrc_exists')}`",
        f"- techfile exists: `{pdk.get('techfile_exists')}`",
        f"- netgen setup exists: `{pdk.get('netgen_setup_exists')}`",
        "",
        "## Recent Magic DRC Log",
        "",
        f"- Log path: `{log.get('path', 'unknown')}`",
        f"- Techfile parse errors: `{log.get('has_techfile_parse_errors')}`",
        f"- Segmentation fault: `{log.get('has_segmentation_fault')}`",
        f"- Recent pipeline failed stage: `{summary.get('failed_stage', 'unknown')}`",
        "",
        "## Recommended Next Actions",
        "",
    ]
    lines.extend(f"- `{action}`" for action in actions)
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    diagnosis = collect_current_diagnosis(args)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(diagnosis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text(render_markdown(diagnosis), encoding="utf-8")
    print(f"environment_status={diagnosis['environment_status']}")
    print(f"suspected_issue={diagnosis['suspected_issue']}")
    print(f"json_output={args.json_output}")
    print(f"markdown_output={args.markdown_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
