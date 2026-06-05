#!/usr/bin/env python3
"""Materialize an AnalogGym candidate action into a SPICE vars file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write .param vars from an AnalogGym recommended candidate.")
    parser.add_argument("--config", type=Path, required=True, help="AnalogGym circuit YAML config.")
    parser.add_argument("--candidates", type=Path, required=True, help="recommended_candidates.json.")
    parser.add_argument("--rank", type=int, default=1, help="Candidate rank to materialize.")
    parser.add_argument("--output", type=Path, required=True, help="Output SPICE vars file.")
    parser.add_argument("--metadata-output", type=Path, required=True, help="Output metadata JSON.")
    return parser.parse_args()


def parameter_order_from_config(config_path: Path) -> list[str]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    devices = config.get("device")
    if not isinstance(devices, dict):
        raise ValueError(f"{config_path} does not contain a device mapping")

    order: list[str] = []
    for device, info in devices.items():
        if not isinstance(info, dict):
            continue
        ranges = info.get("range")
        if not isinstance(ranges, dict):
            continue
        for param in ranges.keys():
            order.append(f"{param}_{device}")
    return order


def select_candidate(candidates_path: Path, rank: int) -> dict[str, Any]:
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    if not isinstance(candidates, list):
        raise ValueError("recommended candidates must be a JSON list")
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate.get("rank") == rank:
            return candidate
    raise ValueError(f"candidate rank {rank} not found")


def format_value(name: str, value: Any) -> str:
    numeric = float(value)
    if name.startswith("M_") and abs(numeric - round(numeric)) < 1e-9:
        return str(int(round(numeric)))
    return f"{numeric:g}"


def write_vars_and_metadata(
    config_path: Path,
    candidates_path: Path,
    rank: int,
    output_path: Path,
    metadata_path: Path,
) -> dict[str, Any]:
    order = parameter_order_from_config(config_path)
    candidate = select_candidate(candidates_path, rank)
    action = candidate.get("action_real")
    if not isinstance(action, list):
        raise ValueError("selected candidate does not contain action_real list")
    if len(action) != len(order):
        raise ValueError(f"action_real length {len(action)} does not match config parameter count {len(order)}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f".param {name}={format_value(name, value)}" for name, value in zip(order, action)]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    metadata = {
        "schema_version": "analoggym_candidate_vars.v1",
        "status": "materialized",
        "config": str(config_path),
        "candidates": str(candidates_path),
        "output": str(output_path),
        "parameter_order": order,
        "parameter_count": len(order),
        "selected_candidate": {
            "rank": candidate.get("rank"),
            "reward": candidate.get("reward"),
            "pm_feasible": candidate.get("pm_feasible"),
            "evaluation_source": candidate.get("evaluation_source"),
            "performance": candidate.get("performance", {}),
        },
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metadata


def main() -> int:
    args = parse_args()
    try:
        metadata = write_vars_and_metadata(
            args.config.resolve(),
            args.candidates.resolve(),
            args.rank,
            args.output.resolve(),
            args.metadata_output.resolve(),
        )
    except Exception as exc:  # noqa: BLE001 - CLI should show actionable data-prep failures.
        raise SystemExit(str(exc)) from exc
    print(f"status={metadata['status']}")
    print(f"rank={metadata['selected_candidate']['rank']}")
    print(f"parameter_count={metadata['parameter_count']}")
    print(f"output={args.output}")
    print(f"metadata={args.metadata_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
