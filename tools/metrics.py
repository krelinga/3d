#!/usr/bin/env python3
"""Derive the STL and the metrics from one built 3MF, in a single load.

OpenSCAD emits 3MF only; the STL and the measurements both come from that same
in-memory mesh, so all three artifacts provably describe one triangulation.
Rendering twice would not: OpenSCAD's output is not deterministic run to run
(upstream #4931), so a second invocation could produce a different mesh.

    metrics.py out/one-inch/one-inch-v1.0.3mf
      -> out/one-inch/one-inch-v1.0.stl
      -> out/one-inch/one-inch-v1.0.metrics.json

Assertions here are build failures, not warnings: a zero-volume or
non-watertight result is broken output, not a small file. Runs inside the
pinned toolchain image -- invoke through bin/python3.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import trimesh


def load_mesh(path: Path) -> trimesh.Trimesh:
    """Load a 3MF as a single concatenated mesh.

    trimesh returns a Scene for 3MF even when there is one object, so this
    always concatenates rather than special-casing the single-geometry case.
    """
    loaded = trimesh.load(str(path), process=False)
    if isinstance(loaded, trimesh.Scene):
        geoms = [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
        if not geoms:
            raise SystemExit(f"metrics: {path}: 3MF contains no triangle meshes")
        return geoms[0] if len(geoms) == 1 else trimesh.util.concatenate(geoms)
    if isinstance(loaded, trimesh.Trimesh):
        return loaded
    raise SystemExit(f"metrics: {path}: unexpected object {type(loaded).__name__}")


def measure(mesh: trimesh.Trimesh) -> dict:
    """The comparable summary of geometry.

    facets is recorded for information only. It is explicitly NOT a drift
    signal: the same input can tessellate differently between two runs of the
    same image, so comparing it would report noise as change.
    """
    return {
        "bbox": [round(float(x), 6) for x in mesh.extents],
        "volume_mm3": round(float(mesh.volume), 6),
        "area_mm2": round(float(mesh.area), 6),
        "facets": int(len(mesh.faces)),
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
    }


def assert_sound(path: Path, mesh: trimesh.Trimesh, m: dict) -> None:
    problems = []
    if not m["watertight"]:
        problems.append("not watertight (would fail in a slicer)")
    if not m["winding_consistent"]:
        problems.append("inconsistent face winding")
    if m["volume_mm3"] <= 0:
        problems.append(f"volume is {m['volume_mm3']} (empty or inside-out result)")
    if m["facets"] <= 0:
        problems.append("no faces")
    if problems:
        raise SystemExit(
            f"metrics: {path}: unusable mesh:\n  - " + "\n  - ".join(problems))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("model", type=Path, help="the built .3mf")
    ap.add_argument("--no-stl", action="store_true", help="metrics only, skip the STL")
    args = ap.parse_args()

    if args.model.suffix != ".3mf":
        raise SystemExit(f"metrics: expected a .3mf, got {args.model}")
    if not args.model.exists():
        # The common cause is not a lost file: OpenSCAD prints "Current top
        # level object is empty", writes nothing, and still exits 0 -- even
        # under --hardwarnings. Failing here is what turns that into a build
        # failure instead of a silently absent artifact.
        raise SystemExit(
            f"metrics: {args.model}: does not exist.\n"
            f"  If the render reported 'Current top level object is empty', "
            f"the model produced no geometry.")

    mesh = load_mesh(args.model)
    m = measure(mesh)
    assert_sound(args.model, mesh, m)

    if not args.no_stl:
        stl = args.model.with_suffix(".stl")
        # Same temp-then-rename discipline the renders use: anything reading
        # this concurrently (the preview server) must never see a partial mesh.
        tmp = stl.with_name(f".tmp-{stl.name}")
        mesh.export(str(tmp))
        tmp.replace(stl)

    metrics_path = args.model.with_suffix(".metrics.json")
    payload = {"source": str(args.model), **m}
    tmp = metrics_path.with_name(f".tmp-{metrics_path.name}")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    tmp.replace(metrics_path)

    bbox = "x".join(f"{v:g}" for v in m["bbox"])
    print(f"  {args.model.name}: {bbox} mm, "
          f"{m['volume_mm3']:g} mm3, {m['facets']} facets", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
