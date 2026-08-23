#!/usr/bin/env python3
"""Generate build-record.json for a release.

The catalog declares *intent* -- what should exist, at what version. This
records *outcome* -- what actually came out, and from which toolchain. It is
generated per release, attached as an asset, and never committed.

The `image` digest is the field that matters. A part's identity is really
(part version, build commit, toolchain digest): if lib/ changes without any
part version changing, two different files can both honestly be labelled
`bracket v2.3`, and only the build record tells them apart afterwards.

Runs inside the pinned toolchain image -- invoke through bin/python3.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import resolve  # noqa: E402


def openscad_version() -> str:
    """Human-readable version, for eyeballing. Tooling keys on the digest."""
    try:
        out = subprocess.run(["openscad", "--version"], capture_output=True,
                             text=True, timeout=60)
        return (out.stdout + out.stderr).strip().splitlines()[0]
    except Exception:
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", required=True)
    ap.add_argument("--release", required=True, help="e.g. one-inch/v1.0")
    ap.add_argument("--commit", required=True)
    ap.add_argument("--image", required=True, help="the toolchain digest")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--build-dir", type=Path, default=Path("out"))
    args = ap.parse_args()

    part = resolve(args.part)
    artifacts = []

    for variant in part.variants:
        stem = part.artifact_stem(variant)
        d = args.build_dir / part.name
        metrics_path = d / f"{stem}.metrics.json"
        if not metrics_path.exists():
            raise SystemExit(f"build_record: {metrics_path} missing -- build first")
        m = json.loads(metrics_path.read_text())

        files, sizes = [], {}
        for ext in ("3mf", "stl"):
            f = d / f"{stem}.{ext}"
            if f.exists():
                files.append(f.name)
                sizes[f"bytes_{ext}"] = f.stat().st_size

        artifacts.append({
            "variant": variant.name,
            "files": files,
            **sizes,
            "bbox": m["bbox"],
            "volume_mm3": m["volume_mm3"],
            "area_mm2": m["area_mm2"],
            # Recorded for information. Explicitly not a drift signal: the same
            # input can tessellate differently between runs of the same image.
            "facets": m["facets"],
            "watertight": m["watertight"],
        })

    record = {
        "release": args.release,
        "part": part.name,
        "version": part.version,
        "commit": args.commit,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "image": args.image,
        "openscad_version": openscad_version(),
        "artifacts": artifacts,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2) + "\n")
    print(f"build_record: wrote {args.out} ({len(artifacts)} artifact(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
