#!/usr/bin/env python3
"""Compare built metrics against a part's most recent release.

Drift detection answers exactly one question: **is a part's declared version
still an honest description of what that part builds?** It is not a correctness
check -- a part can drift and be perfectly fine, which is the normal outcome of
improving a shared module. The only thing drift ever asks for is a decision
about whether to re-tag.

Comparison is tolerance-based, never equality. OpenSCAD's output is not
deterministic run to run (#4931), so equality would report noise as change.
Facet count is deliberately ignored for the same reason.

    drift.py --baselines baselines/ --out out/            # report
    drift.py --baselines baselines/ --out out/ --json     # machine-readable

Runs inside the pinned toolchain image -- invoke through bin/python3.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import load_or_die  # noqa: E402

# Tolerances from docs/design/initial-design.md.
BBOX_ABS_TOL = 1e-3      # mm
VOLUME_REL_TOL = 1e-4
AREA_REL_TOL = 1e-4


def _rel_change(new: float, old: float) -> float:
    if old == 0:
        return 0.0 if new == 0 else float("inf")
    return abs(new - old) / abs(old)


def compare(current: dict, baseline: dict) -> list[str]:
    """Return human-readable reasons the geometry moved, or [] if it did not."""
    reasons: list[str] = []

    cur_bbox, base_bbox = current.get("bbox", []), baseline.get("bbox", [])
    if len(cur_bbox) != len(base_bbox):
        reasons.append(f"bbox shape changed: {base_bbox} -> {cur_bbox}")
    else:
        moved = [(i, b, c) for i, (b, c) in enumerate(zip(base_bbox, cur_bbox))
                 if abs(c - b) > BBOX_ABS_TOL]
        if moved:
            reasons.append(
                "bbox " + " ".join(f"{'xyz'[i]} {b:g}->{c:g}" for i, b, c in moved))

    for key, tol, label in (("volume_mm3", VOLUME_REL_TOL, "volume"),
                            ("area_mm2", AREA_REL_TOL, "area")):
        cur, base = current.get(key), baseline.get(key)
        if cur is None or base is None:
            continue
        change = _rel_change(cur, base)
        if change > tol:
            pct = ((cur - base) / base * 100) if base else float("inf")
            reasons.append(f"{label} {base:g} -> {cur:g} ({pct:+.2f}%)")

    # facets is NOT compared: it varies between runs of the same image.
    return reasons


def load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("out"),
                    help="tree of freshly built metrics (default: out)")
    ap.add_argument("--baselines", type=Path, required=True,
                    help="directory of <part>.build-record.json from the last release")
    ap.add_argument("--image", default="",
                    help="current toolchain digest; if it differs from a baseline's, "
                         "that part is reported as a rebaseline rather than drift")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of prose")
    args = ap.parse_args()

    parts = load_or_die()
    drifted: list[dict] = []
    unreleased: list[str] = []
    incomparable: list[str] = []
    toolchain_moved: list[str] = []
    unchanged: list[str] = []

    for part in sorted(parts, key=lambda p: p.name):
        record = load_json(args.baselines / f"{part.name}.build-record.json")
        if record is None:
            unreleased.append(part.name)
            continue

        base_artifacts = {a.get("variant"): a for a in record.get("artifacts", [])}
        base_image = record.get("image", "")
        # A toolchain change moves metrics on nearly every part at once. Those
        # are grouped into one repo-wide rebaseline rather than N drift reports,
        # or the first pin bump buries the signal it was meant to produce.
        image_differs = bool(args.image and base_image and args.image != base_image)

        part_reasons: list[str] = []
        for variant in part.variants:
            stem = part.artifact_stem(variant)
            current = load_json(args.out / part.name / f"{stem}.metrics.json")
            if current is None:
                part_reasons.append(f"{variant.name}: not built")
                continue
            base = base_artifacts.get(variant.name)
            if base is None or "volume_mm3" not in base:
                incomparable.append(f"{part.name}/{variant.name}")
                continue
            reasons = compare(current, base)
            if reasons:
                part_reasons += [f"{variant.name}: {r}" for r in reasons]

        if not part_reasons:
            unchanged.append(part.name)
            continue
        entry = {
            "part": part.name,
            "declared_version": part.version,
            "released_version": record.get("version"),
            "reasons": part_reasons,
            "version_bumped": part.version != record.get("version"),
        }
        if image_differs:
            entry["baseline_image"] = base_image
            toolchain_moved.append(part.name)
        drifted.append(entry)

    # Drift is only interesting when the version did NOT move: a bumped version
    # is already an honest description of different output.
    real_drift = [d for d in drifted if not d["version_bumped"]]

    if args.json:
        print(json.dumps({
            "drift": real_drift,
            "changed_but_version_bumped": [d for d in drifted if d["version_bumped"]],
            "toolchain_moved": toolchain_moved,
            "unreleased": unreleased,
            "incomparable": incomparable,
            "unchanged": unchanged,
            "rebaseline": bool(toolchain_moved),
        }, indent=2))
        return 0

    if toolchain_moved:
        print(f"TOOLCHAIN MOVED to {args.image}")
        print(f"  {len(toolchain_moved)} part(s) show geometry change; review and "
              f"re-tag as needed. This is one rebaseline, not {len(toolchain_moved)} "
              f"separate drifts.\n")
    if real_drift:
        print("DRIFT -- output changed but the declared version did not:\n")
        for d in real_drift:
            print(f"  {d['part']} (still v{d['declared_version']}, "
                  f"released v{d['released_version']})")
            for r in d["reasons"]:
                print(f"    - {r}")
        print()
    for label, names in (("unreleased, no baseline", unreleased),
                         ("baseline incomparable", incomparable)):
        if names:
            print(f"{label}: {', '.join(names)}")
    if unchanged:
        print(f"unchanged: {len(unchanged)} part(s)")
    if not real_drift and not toolchain_moved:
        print("\nNo drift.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
