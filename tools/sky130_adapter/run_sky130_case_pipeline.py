#!/usr/bin/env python3
"""User-facing CLI wrapper for the Sky130 MAGICAL bridge/remap pipeline."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
SHELL_PIPELINE = SCRIPT_DIR / "run_sky130_case_pipeline.sh"
DEFAULT_SKY130A = Path(
    Path.home()
    / ".ciel/ciel/sky130/versions"
    / "7b70722e33c03fcb5dabcf4d479fb0822d9251c9/sky130A"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run MAGICAL Sky130 bridge/remap flow from a clean or xschem raw netlist."
    )
    parser.add_argument("--netlist", type=Path, required=True, help="Input clean MAGICAL or xschem raw netlist.")
    parser.add_argument("--top-cell", required=True, help="Top subckt/cell name.")
    parser.add_argument("--case-name", help="Case name. Defaults to --top-cell.")
    parser.add_argument("--vdd", required=True, help="Top-level power net name.")
    parser.add_argument("--vss", required=True, help="Top-level ground net name.")
    parser.add_argument("--out-dir", type=Path, help="Output directory. Defaults to generated/sky130_cases/<case>.")
    parser.add_argument(
        "--convert-xschem",
        choices=("yes", "no"),
        default="no",
        help="Convert xschem/ngspice Sky130 raw netlist before running MAGICAL.",
    )
    parser.add_argument("--config", type=Path, help="Existing MAGICAL JSON config.")
    parser.add_argument("--case-dir", type=Path, help="Existing or generated case directory.")
    parser.add_argument("--output-node", help="Optional output node for PEX summary focus.")
    parser.add_argument(
        "--net-role",
        action="append",
        default=[],
        metavar="NET=ROLE",
        help="Annotate a net role for parasitic_summary.json. May be repeated.",
    )
    parser.add_argument("--docker-image", help="Override Docker image passed to shell pipeline.")
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="Print generated inputs even if preflight dependency checks fail.",
    )
    return parser.parse_args()


def repo_path(path: Path) -> Path:
    path = path.expanduser()
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def rel_or_abs(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def command_path(names: tuple[str, ...]) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def preflight(env: dict[str, str]) -> list[str]:
    errors: list[str] = []
    if not command_path(("docker",)):
        errors.append("Docker not found: install docker or add it to PATH.")
    if not command_path(("magic",)):
        errors.append("Magic not found: install magic or add it to PATH.")
    if not command_path(("netgen", "netgen-lvs")):
        errors.append("netgen-lvs/netgen not found: install netgen-lvs or netgen.")

    sky130a = Path(env.get("SKY130A", str(DEFAULT_SKY130A))).expanduser()
    if not sky130a.is_dir():
        errors.append(f"SKY130A path invalid: {sky130a}")
    magicrc = sky130a / "libs.tech/magic/sky130A.magicrc"
    if not magicrc.is_file():
        errors.append(f"sky130A.magicrc not found: {magicrc}")
    setup = sky130a / "libs.tech/netgen/sky130A_setup.tcl"
    if not setup.is_file():
        errors.append(f"sky130A_setup.tcl not found: {setup}")
    return errors


def read_subckt_ports(netlist: Path, top_cell: str) -> list[str]:
    pattern = re.compile(rf"^\s*\.?subckt\s+{re.escape(top_cell)}\b\s*(.*)$", re.IGNORECASE)
    for line in netlist.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("*"):
            line = line.lstrip("*").strip()
        match = pattern.match(line)
        if match:
            return match.group(1).split()
    return []


def rel_from_case(case_dir: Path, path: Path) -> str:
    return os.path.relpath(path.resolve(), case_dir.resolve())


def write_config(config: Path, case_dir: Path, netlist_name: str, vdd: str, vss: str) -> None:
    tech_dir = REPO_ROOT / "examples/sky130PDK"
    data = {
        "spectre_netlist": netlist_name,
        "resultDir": "./",
        "techfile": rel_from_case(case_dir, tech_dir / "sky130.techfile"),
        "simple_tech_file": rel_from_case(case_dir, tech_dir / "sky130.techfile.simple"),
        "lef": rel_from_case(case_dir, tech_dir / "sky130.lef"),
        "vddNetNames": [vdd],
        "vssNetNames": [vss],
    }
    config.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")


def parse_summary(summary: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not summary.is_file():
        return values
    row = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|")
    for line in summary.read_text(encoding="utf-8", errors="replace").splitlines():
        match = row.match(line)
        if not match:
            continue
        key = match.group(1).strip()
        value = match.group(2).strip()
        if key not in {"Field", "---"}:
            values[key] = value
    return values


def print_result(case_name: str, top_cell: str, out_dir: Path) -> None:
    summary = out_dir / "summary.md"
    values = parse_summary(summary)
    final_gds = ""
    # The shell summary lists the final GDS under KEY_OUTPUTS, not the table.
    expected_case_dir = None
    if summary.is_file():
        for line in summary.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("- Pinned-shapes GDS:"):
                final_gds = line.split("`", 2)[1]
            elif line.startswith("- Case directory:"):
                expected_case_dir = line.split("`", 2)[1]
    if not final_gds:
        final_gds = str((Path(expected_case_dir or ".") / f"{top_cell}.sky130.pinned_shapes.gds").resolve())

    print()
    print("SKY130_PIPELINE_RESULT")
    print(f"CASE_NAME={case_name}")
    print(f"TOP_CELL={top_cell}")
    print(f"FINAL_GDS={final_gds}")
    print(f"DRC_COUNT={values.get('DRC_COUNT', 'unknown')}")
    print(f"CONNECTIVITY_LVS_MATCH={values.get('CONNECTIVITY_LVS_MATCH', 'unknown')}")
    print(f"PEX_CAPS={values.get('PEX_CAPS', 'unknown')}")
    print(f"PEX_TOTAL_CAP_FF={values.get('PEX_TOTAL_CAP_FF', 'unknown')}")
    print(f"DRC_REPORT={out_dir / 'magic_drc.log'}")
    print(f"RAW_EXTRACTED_NETLIST={out_dir / (top_cell + '_extracted.raw.spice')}")
    print(f"CONNECTIVITY_LVS_RESULT={out_dir / 'lvs_result_summary.md'}")
    print(f"PEX_SUMMARY={out_dir / 'pex_summary.md'}")
    print(f"PARASITIC_SUMMARY_JSON={out_dir / 'parasitic_summary.json'}")
    print(f"CIRCUIT_GRAPH_JSON={out_dir / 'circuit_graph.json'}")
    print(f"SAMPLE_RECORD_JSON={out_dir / 'sample_record.json'}")
    print(f"KLAYOUT_GDS={final_gds}")
    print(f"SUMMARY_MD={summary}")


def main() -> int:
    args = parse_args()
    case_name = args.case_name or args.top_cell
    netlist = repo_path(args.netlist)
    if not netlist.is_file():
        print(f"error: input netlist not found: {netlist}", file=sys.stderr)
        return 2

    case_dir = repo_path(args.case_dir) if args.case_dir else REPO_ROOT / "generated/user_cases" / case_name
    out_dir = repo_path(args.out_dir) if args.out_dir else REPO_ROOT / "generated/sky130_cases" / case_name
    case_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    copied_input = case_dir / netlist.name
    if netlist.resolve() != copied_input.resolve():
        shutil.copyfile(netlist, copied_input)

    magical_netlist = copied_input
    raw_netlist = copied_input
    if args.convert_xschem == "yes":
        magical_netlist = case_dir / f"{copied_input.stem}_magical.sp"

    config = repo_path(args.config) if args.config else case_dir / f"{case_name}.json"
    if not args.config:
        write_config(config, case_dir, magical_netlist.name, args.vdd, args.vss)

    if args.convert_xschem == "no":
        ports = read_subckt_ports(magical_netlist, args.top_cell)
        missing_ports = [net for net in (args.vdd, args.vss) if net not in ports]
        if missing_ports:
            print(
                "warning: top subckt ports do not explicitly include "
                + ", ".join(missing_ports)
                + "; MAGICAL/Sky130 LVS expects power nets as top ports.",
                file=sys.stderr,
            )

    env = os.environ.copy()
    if args.docker_image:
        env["DOCKER_IMAGE"] = args.docker_image
    env.setdefault("SKY130A", str(DEFAULT_SKY130A))
    env.setdefault("PDK_ROOT", str(Path(env["SKY130A"]).expanduser().resolve().parent))
    errors = preflight(env)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        print(f"generated_case_dir={case_dir}", file=sys.stderr)
        print(f"generated_config={config}", file=sys.stderr)
        if not args.keep_going:
            return 2

    cmd = [
        str(SHELL_PIPELINE),
        "--case-name",
        case_name,
        "--case-dir",
        rel_or_abs(case_dir),
        "--top-cell",
        args.top_cell,
        "--magical-netlist",
        rel_or_abs(magical_netlist),
        "--config",
        rel_or_abs(config),
        "--vdd",
        args.vdd,
        "--vss",
        args.vss,
        "--out-dir",
        rel_or_abs(out_dir),
        "--convert-xschem",
        args.convert_xschem,
    ]
    if args.convert_xschem == "yes":
        cmd.extend(["--raw-netlist", rel_or_abs(raw_netlist)])
    if args.output_node:
        cmd.extend(["--output-node", args.output_node])
    for net_role in args.net_role:
        cmd.extend(["--net-role", net_role])

    print("RUN:", " ".join(cmd))
    status = subprocess.run(cmd, cwd=REPO_ROOT, env=env, check=False).returncode
    print_result(case_name, args.top_cell, out_dir)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
