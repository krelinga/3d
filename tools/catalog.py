#!/usr/bin/env python3
"""Load and validate the catalog: one entry.yaml per part.

The directory listing *is* the catalog (docs/design/initial-design.md), so this
module's job is to turn `parts/**/entry.yaml` into structured records and to
reject every way that tree can be malformed. It is imported by the other tools
and run directly by `make check`.

Runs inside the pinned toolchain image (it needs PyYAML); invoke it through
bin/python3 rather than the devcontainer's own python3.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

PARTS_DIR = Path("parts")

DIR_NAME_RE = re.compile(r"^[a-z0-9-]+$")
# Accepts 1, 1.0 or 1.2.3. Whatever is declared is normalised to three
# components (see normalize_version): one canonical form reaches tags,
# filenames and build records, so "1.0" and "1.0.0" can never name two
# different releases of the same thing.
VERSION_RE = re.compile(r"^\d+(\.\d+){0,2}$")
VARIANT_NAME_RE = re.compile(r"^[a-z0-9_]+$")

TOP_LEVEL_KEYS = {
    "version", "status", "description", "variants", "camera", "print", "hardware",
}
REQUIRED_KEYS = {"version", "status", "description", "camera"}
STATUSES = {"active", "deprecated"}


def normalize_version(declared: str) -> str:
    """Pad a declared version to major.minor.patch.

    Padding happens once, here, rather than at each use site: the version is
    identity-bearing (it is in the tag and in every artifact filename), so two
    spellings of the same version must not be able to produce two different
    tags.
    """
    parts = declared.split(".")
    parts += ["0"] * (3 - len(parts))
    return ".".join(parts)


@dataclass
class Variant:
    name: str
    param_set: str | None  # None for a single-variant part

    @property
    def suffix(self) -> str:
        """The variant's contribution to an artifact filename.

        Empty for single-variant parts: `spool-holder-v1.4.3mf`, not
        `spool-holder-v1.4-default.3mf`.
        """
        return f"-{self.name}" if self.param_set is not None else ""


@dataclass
class Part:
    name: str            # leaf directory name; never the path
    path: Path
    version: str         # normalised to major.minor.patch; use this everywhere
    status: str
    description: str
    camera: list[float]
    variants: list[Variant]
    print_meta: dict = field(default_factory=dict)
    hardware: list[str] = field(default_factory=list)
    root: Path = PARTS_DIR
    declared_version: str = ""   # exactly as written in entry.yaml

    @property
    def source(self) -> Path:
        return self.path / "source.scad"

    @property
    def params(self) -> Path | None:
        p = self.path / "params.json"
        return p if p.exists() else None

    @property
    def category(self) -> str | None:
        """Path from parts/ to the part's parent, or None if top-level.

        Presentation only -- the README index groups by it. Nothing about a
        part's identity depends on it.
        """
        rel = self.path.relative_to(self.root).parent
        return None if str(rel) == "." else str(rel)

    def artifact_stem(self, variant: Variant) -> str:
        return f"{self.name}-v{self.version}{variant.suffix}"


class CatalogError(Exception):
    pass


def _err(errors: list[str], path: Path, msg: str) -> None:
    errors.append(f"{path}: {msg}")


def _validate_entry(entry_path: Path, raw, errors: list[str]) -> dict | None:
    if not isinstance(raw, dict):
        _err(errors, entry_path, "must be a YAML mapping")
        return None

    unknown = set(raw) - TOP_LEVEL_KEYS
    if unknown:
        # Catches `paarams:` and friends, which would otherwise be silently ignored.
        _err(errors, entry_path, f"unrecognized top-level keys: {sorted(unknown)}")
    missing = REQUIRED_KEYS - set(raw)
    if missing:
        _err(errors, entry_path, f"missing required keys: {sorted(missing)}")

    version = raw.get("version")
    if version is not None:
        if not isinstance(version, str):
            # Unquoted, YAML reads 2.10 as a float and silently makes it 2.1,
            # which then fails to match tag <part>/v2.10.
            _err(errors, entry_path,
                 f"version must be a quoted string, got {type(version).__name__} "
                 f"({version!r}) -- write version: \"{version}\"")
        elif not VERSION_RE.match(version):
            _err(errors, entry_path,
                 f"version {version!r} must match N, N.N or N.N.N")

    status = raw.get("status")
    if status is not None and status not in STATUSES:
        _err(errors, entry_path, f"status must be one of {sorted(STATUSES)}, got {status!r}")

    camera = raw.get("camera")
    if camera is not None:
        if (not isinstance(camera, list) or len(camera) != 7
                or not all(isinstance(n, (int, float)) and not isinstance(n, bool)
                           for n in camera)):
            _err(errors, entry_path, "camera must be a list of exactly 7 numbers")

    return raw


def _validate_variants(part_dir: Path, raw: dict, errors: list[str]) -> list[Variant]:
    entry_path = part_dir / "entry.yaml"
    params_path = part_dir / "params.json"
    declared = raw.get("variants")
    has_params = params_path.exists()

    if declared is None and not has_params:
        # Single-variant part: one artifact, no -p/-P, no variant suffix.
        return [Variant(name=part_dir.name, param_set=None)]

    if declared is None and has_params:
        _err(errors, entry_path, "params.json exists but no variants: are declared")
        return []
    if declared is not None and not has_params:
        _err(errors, entry_path, "variants: are declared but params.json is missing")
        return []

    if not isinstance(declared, list) or not declared:
        _err(errors, entry_path, "variants: must be a non-empty list")
        return []

    param_sets: set[str] = set()
    try:
        params_doc = json.loads(params_path.read_text())
        param_sets = set(params_doc.get("parameterSets", {}))
    except (json.JSONDecodeError, OSError) as exc:
        _err(errors, params_path, f"unreadable: {exc}")

    variants: list[Variant] = []
    seen: set[str] = set()
    for item in declared:
        if not isinstance(item, dict) or "name" not in item or "param_set" not in item:
            _err(errors, entry_path, f"each variant needs name and param_set: {item!r}")
            continue
        name, ps = item["name"], item["param_set"]
        if not isinstance(name, str) or not VARIANT_NAME_RE.match(name):
            # Variant names end up in filenames.
            _err(errors, entry_path, f"variant name {name!r} must match ^[a-z0-9_]+$")
            continue
        if name in seen:
            _err(errors, entry_path, f"duplicate variant name {name!r}")
            continue
        seen.add(name)
        if param_sets and ps not in param_sets:
            _err(errors, params_path,
                 f"variant {name!r} names param_set {ps!r}, which is not defined")
        variants.append(Variant(name=name, param_set=ps))
    return variants


def load(root: Path = PARTS_DIR) -> tuple[list[Part], list[str]]:
    """Return (parts, errors). Never raises for catalog problems."""
    errors: list[str] = []
    if not root.exists():
        return [], [f"{root}: does not exist"]

    entries = sorted(root.rglob("entry.yaml"))
    part_dirs = {e.parent for e in entries}
    parts: list[Part] = []

    for entry_path in entries:
        part_dir = entry_path.parent

        # A directory is a category or a part, never both.
        nested = [e for e in part_dir.rglob("entry.yaml") if e != entry_path]
        if nested:
            _err(errors, part_dir,
                 "is a part but contains descendant entry.yaml: "
                 f"{[str(n) for n in nested]}")

        if not (part_dir / "source.scad").exists():
            _err(errors, part_dir, "has entry.yaml but no source.scad")

        try:
            raw = yaml.safe_load(entry_path.read_text())
        except yaml.YAMLError as exc:
            _err(errors, entry_path, f"invalid YAML: {exc}")
            continue

        validated = _validate_entry(entry_path, raw, errors)
        if validated is None:
            continue
        variants = _validate_variants(part_dir, validated, errors)

        parts.append(Part(
            name=part_dir.name,
            path=part_dir,
            version=normalize_version(str(validated.get("version", "0"))),
            declared_version=str(validated.get("version", "")),
            status=validated.get("status", "active"),
            description=validated.get("description", ""),
            camera=list(validated.get("camera") or []),
            variants=variants,
            print_meta=validated.get("print") or {},
            hardware=list(validated.get("hardware") or []),
            root=root,
        ))

    # Every directory under parts/ is a category or a part, and category
    # directories hold only directories and must contain a part somewhere.
    for d in sorted(p for p in root.rglob("*") if p.is_dir()):
        if d in part_dirs:
            continue
        if any(child.is_file() for child in d.iterdir()):
            _err(errors, d, "is a category but contains files; categories hold only directories")
        if not any(e.parent != d and d in e.parents for e in entries):
            _err(errors, d, "is a category containing no parts (typo or abandoned?)")
        if not DIR_NAME_RE.match(d.name):
            _err(errors, d, f"directory name {d.name!r} must match ^[a-z0-9-]+$")

    for d in sorted(part_dirs):
        if not DIR_NAME_RE.match(d.name):
            _err(errors, d, f"part name {d.name!r} must match ^[a-z0-9-]+$")

    # Part names are tag prefixes and filename components, so they must be
    # globally unique even though their paths differ.
    by_name: dict[str, list[Path]] = {}
    for p in parts:
        by_name.setdefault(p.name, []).append(p.path)
    for name, paths in sorted(by_name.items()):
        if len(paths) > 1:
            errors.append(
                f"part name {name!r} is used by multiple directories: "
                f"{[str(x) for x in paths]}")

    return parts, errors


def load_or_die(root: Path = PARTS_DIR) -> list[Part]:
    parts, errors = load(root)
    if errors:
        for e in errors:
            print(f"catalog: {e}", file=sys.stderr)
        raise SystemExit(1)
    return parts


def resolve(name: str, root: Path = PARTS_DIR) -> Part:
    """name -> Part. A part's path cannot be constructed from its name."""
    for p in load_or_die(root):
        if p.name == name:
            return p
    raise SystemExit(f"catalog: no part named {name!r}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate or query the parts catalog.")
    ap.add_argument("--validate", action="store_true", help="validate and report")
    ap.add_argument("--list", action="store_true", help="list part names")
    ap.add_argument("--path", metavar="NAME", help="print the directory for a part")
    ap.add_argument("--version", metavar="NAME", help="print the declared version for a part")
    ap.add_argument("--json", action="store_true", help="dump the whole catalog as JSON")
    ap.add_argument("--root", default=str(PARTS_DIR),
                    help="catalog root (default: parts) -- mainly for testing")
    args = ap.parse_args()
    root = Path(args.root)

    if args.path:
        print(resolve(args.path, root).path)
        return 0
    if args.version:
        print(resolve(args.version, root).version)
        return 0

    parts, errors = load(root)
    if errors:
        for e in errors:
            print(f"catalog: {e}", file=sys.stderr)
        print(f"\n{len(errors)} problem(s) found.", file=sys.stderr)
        return 1

    if args.list:
        for p in parts:
            print(p.name)
    elif args.json:
        print(json.dumps([{
            "name": p.name, "path": str(p.path), "version": p.version,
            "declared_version": p.declared_version,
            "status": p.status, "description": p.description,
            "category": p.category, "camera": p.camera,
            "variants": [{"name": v.name, "param_set": v.param_set} for v in p.variants],
            "print": p.print_meta, "hardware": p.hardware,
        } for p in parts], indent=2))
    elif args.validate:
        n = sum(len(p.variants) for p in parts)
        print(f"catalog OK: {len(parts)} part(s), {n} variant(s)")
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
