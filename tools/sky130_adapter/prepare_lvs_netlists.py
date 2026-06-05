#!/usr/bin/env python3
"""Prepare raw and connectivity netlists for Sky130 LVS trials."""

from __future__ import annotations

import argparse
import re
import shutil
from collections import Counter
from pathlib import Path


REMOVED_PROPERTIES = {"ad", "as", "pd", "ps"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare Sky130 LVS netlist variants.")
    parser.add_argument("--source", type=Path, required=True, help="Input source netlist.")
    parser.add_argument("--extracted", type=Path, required=True, help="Magic raw extracted netlist.")
    parser.add_argument("--out-dir", type=Path, required=True, help="Output directory.")
    parser.add_argument("--report", type=Path, help="Preparation report path.")
    parser.add_argument("--prefix", default="inverter_core", help="Output filename prefix.")
    parser.add_argument(
        "--rename",
        action="append",
        default=[],
        metavar="OLD=NEW",
        help="Explicit net rename for connectivity LVS. May be repeated.",
    )
    return parser.parse_args()


def parse_renames(rename_args: list[str]) -> dict[str, str]:
    renames: dict[str, str] = {}
    for item in rename_args:
        if "=" not in item:
            raise ValueError(f"invalid rename '{item}', expected OLD=NEW")
        old, new = item.split("=", 1)
        if not old or not new:
            raise ValueError(f"invalid rename '{item}', expected OLD=NEW")
        renames[old] = new
    return renames


def normalize_length(value: str) -> str:
    value = value.lower().removeprefix("l=")
    if value.endswith("n"):
        return f"{float(value[:-1]) / 1000.0:g}"
    if value.endswith("u"):
        return value[:-1]
    return value


def normalize_width(value: str) -> str:
    value = value.lower().removeprefix("w=")
    if value.endswith("u"):
        return value[:-1]
    return value


def source_to_connectivity(lines: list[str]) -> tuple[list[str], bool, bool]:
    output: list[str] = []
    saw_subckt = False
    saw_ends = False
    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()
        if not stripped:
            output.append(line)
            continue
        if lower.startswith("subckt "):
            output.append(re.sub(r"^\s*subckt\b", ".subckt", line, flags=re.IGNORECASE))
            saw_subckt = True
            continue
        if lower.startswith(".subckt "):
            output.append(line)
            saw_subckt = True
            continue
        if re.match(r"^ends(\s+|$)", lower):
            output.append(re.sub(r"^\s*ends\b", ".ends", line, flags=re.IGNORECASE))
            saw_ends = True
            continue
        if lower.startswith(".ends"):
            output.append(line)
            saw_ends = True
            continue
        if re.match(r"^[Cc]\S+\s+", stripped):
            flattened = stripped.replace("(", " ").replace(")", " ")
            output.append(" ".join(flattened.split()) + "\n")
            continue
        if re.match(r"^[Mm]\S+\s+", stripped):
            flattened = stripped.replace("(", " ").replace(")", " ")
            tokens = flattened.split()
            if len(tokens) < 6:
                output.append(line)
                continue
            inst = "X" + tokens[0][1:]
            width = ""
            length = ""
            for token in tokens[6:]:
                key = token.split("=", 1)[0].lower()
                if key == "w":
                    width = normalize_width(token)
                elif key == "l":
                    length = normalize_length(token)
            suffix = []
            if width:
                suffix.append(f"w={width}")
            if length:
                suffix.append(f"l={length}")
            output.append(
                " ".join([inst, tokens[1], tokens[2], tokens[3], tokens[4], tokens[5]] + suffix)
                + "\n"
            )
            continue
        output.append(line)
    return output, saw_subckt, saw_ends


def apply_renames(line: str, renames: dict[str, str]) -> str:
    for old, new in renames.items():
        line = line.replace(old, new)
    return line


def extracted_to_connectivity(
    lines: list[str], renames: dict[str, str]
) -> tuple[list[str], int, Counter[str], int]:
    output: list[str] = []
    deleted_caps = 0
    removed_props: Counter[str] = Counter()
    renamed_lines = 0
    for line in lines:
        stripped = line.strip()
        if re.match(r"^[Cc]\S*\s+", stripped):
            deleted_caps += 1
            continue
        renamed = apply_renames(line, renames)
        if renamed != line:
            renamed_lines += 1
        if re.match(r"^[Xx]\S+\s+", renamed.strip()):
            kept = []
            for token in renamed.split():
                key = token.split("=", 1)[0].lower()
                if key in REMOVED_PROPERTIES:
                    removed_props[key] += 1
                    continue
                kept.append(token)
            renamed = " ".join(kept) + "\n"
        output.append(renamed)
    return output, deleted_caps, removed_props, renamed_lines


def write_report(
    report_path: Path,
    source_path: Path,
    extracted_path: Path,
    raw_copy: Path,
    source_conn: Path,
    extracted_conn: Path,
    deleted_caps: int,
    removed_props: Counter[str],
    renames: dict[str, str],
    renamed_lines: int,
) -> None:
    lines = [
        "# LVS Preparation Report",
        "",
        "## Outputs",
        "",
        f"- Input source netlist: `{source_path}`",
        f"- Input Magic raw extracted netlist: `{extracted_path}`",
        f"- Raw extracted netlist copy: `{raw_copy}`",
        f"- Connectivity source netlist: `{source_conn}`",
        f"- Connectivity extracted netlist: `{extracted_conn}`",
        "",
        "## Connectivity Normalization",
        "",
        f"- Deleted parasitic capacitor lines: {deleted_caps}",
        "- Removed MOS properties:",
    ]
    for prop in sorted(REMOVED_PROPERTIES):
        lines.append(f"  - `{prop}`: {removed_props.get(prop, 0)}")
    lines.extend(["", "## Net Renames", ""])
    if renames:
        lines.extend(["| Extracted net | Connectivity net |", "| --- | --- |"])
        for old, new in sorted(renames.items()):
            lines.append(f"| `{old}` | `{new}` |")
        lines.append(f"\nRenamed lines: {renamed_lines}")
    else:
        lines.append("- Net rename enabled: no")
        lines.append("- Power-net fixed baseline no longer requires `a_n15_90#` rename.")
    lines.extend(
        [
            "",
            "## LVS Type",
            "",
            "This output is for connectivity LVS, not parasitic-aware LVS.",
            "The raw Magic extraction is preserved separately so parasitic information is not lost.",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    source_path = args.source.resolve()
    extracted_path = args.extracted.resolve()
    out_dir = args.out_dir.resolve()
    report_path = (args.report or out_dir / "lvs_preparation_report.md").resolve()
    renames = parse_renames(args.rename)

    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if not extracted_path.is_file():
        raise FileNotFoundError(extracted_path)

    out_dir.mkdir(parents=True, exist_ok=True)
    raw_copy = out_dir / f"{args.prefix}_extracted.raw.spice"
    extracted_conn = out_dir / f"{args.prefix}_extracted.connectivity.spice"
    source_conn = out_dir / f"{args.prefix}_source.connectivity.spice"

    shutil.copyfile(extracted_path, raw_copy)

    source_lines = source_path.read_text(encoding="utf-8").splitlines(keepends=True)
    source_output, saw_subckt, saw_ends = source_to_connectivity(source_lines)
    if not saw_subckt or not saw_ends:
        raise ValueError(f"source netlist lacks subckt/ends: {source_path}")
    source_conn.write_text("".join(source_output), encoding="utf-8")

    extracted_lines = extracted_path.read_text(encoding="utf-8").splitlines(keepends=True)
    extracted_output, deleted_caps, removed_props, renamed_lines = extracted_to_connectivity(
        extracted_lines, renames
    )
    extracted_conn.write_text("".join(extracted_output), encoding="utf-8")

    write_report(
        report_path,
        source_path,
        extracted_path,
        raw_copy,
        source_conn,
        extracted_conn,
        deleted_caps,
        removed_props,
        renames,
        renamed_lines,
    )

    print(f"raw_extracted={raw_copy}")
    print(f"connectivity_source={source_conn}")
    print(f"connectivity_extracted={extracted_conn}")
    print(f"report={report_path}")
    print(f"deleted_caps={deleted_caps}")
    print("net_renames=yes" if renames else "net_renames=no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
