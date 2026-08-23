#!/usr/bin/env python3
"""Render a part's print metadata into a PRINT.md release asset.

This is what keeps `print:` and `hardware:` from rotting. Metadata nothing
reads decays silently; rendering it into an asset means a downloaded artifact
is self-describing, and means an unused field is visibly unused -- at which
point it should be deleted from the schema rather than kept.

Runs inside the pinned toolchain image -- invoke through bin/python3.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import resolve  # noqa: E402

FIELD_LABELS = {
    "layer_height": ("Layer height", "mm"),
    "infill": ("Infill", "%"),
    "supports": ("Supports", ""),
    "orientation": ("Orientation", ""),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    part = resolve(args.part)
    lines = [
        f"# {part.name} v{part.version}",
        "",
        part.description,
        "",
    ]

    if part.print_meta:
        lines += ["## Suggested print settings", ""]
        for key, value in part.print_meta.items():
            label, unit = FIELD_LABELS.get(key, (key.replace("_", " ").capitalize(), ""))
            if isinstance(value, bool):
                value = "yes" if value else "no"
            lines.append(f"- **{label}:** {value}{(' ' + unit) if unit else ''}")
        lines.append("")

    if part.hardware:
        lines += ["## Hardware", ""]
        lines += [f"- {h}" for h in part.hardware]
        lines.append("")

    variants = [v for v in part.variants if v.param_set is not None]
    if variants:
        lines += ["## Variants in this release", ""]
        lines += [f"- `{v.name}`" for v in variants]
        lines.append("")

    lines += [
        "## Files",
        "",
        "Prefer the **3MF**: it carries units, which removes the most common",
        "cause of a model printing at the wrong scale. The STL is provided for",
        "older tooling.",
        "",
        "`build-record.json` records the exact commit and toolchain digest that",
        "produced these meshes.",
        "",
    ]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines))
    print(f"print_md: wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
