#!/usr/bin/env python3
"""Regenerate the README index block from the catalog.

Fills the region between the markers and leaves everything outside them --
including the hand-written "Build your own variant" section -- untouched.

    render_index.py            # rewrite README.md in place
    render_index.py --check    # non-zero if the block is stale (for CI)

Runs inside the pinned toolchain image -- invoke through bin/python3.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import Part, load_or_die  # noqa: E402

BEGIN = "<!-- BEGIN INDEX -->"
END = "<!-- END INDEX -->"
THUMBS = Path("thumbnails")


def release_url(repo: str, part: Part) -> str:
    return f"https://github.com/{repo}/releases/tag/{part.name}%2Fv{part.version}"


def thumb_for(part: Part) -> str:
    """Prefer the first variant's thumbnail; blank if it has not been rendered."""
    if not part.variants:
        return ""
    png = THUMBS / part.name / f"{part.variants[0].name}.png"
    return f"![{part.name}]({png})" if png.exists() else ""


def table(parts: list[Part], repo: str) -> list[str]:
    rows = ["| Part | Version | Description | Release | Thumbnail |",
            "|---|---|---|---|---|"]
    for p in parts:
        rows.append(
            f"| `{p.name}` | {p.version} | {p.description} | "
            f"[{p.name}/v{p.version}]({release_url(repo, p)}) | {thumb_for(p)} |")
    return rows


def render(parts: list[Part], repo: str) -> str:
    active = [p for p in parts if p.status == "active"]
    deprecated = [p for p in parts if p.status == "deprecated"]

    # One section per category, in path order, with uncategorized parts last.
    by_cat: dict[str | None, list[Part]] = {}
    for p in sorted(active, key=lambda p: p.name):
        by_cat.setdefault(p.category, []).append(p)

    lines: list[str] = []
    for cat in sorted((c for c in by_cat if c is not None)):
        lines += [f"### {cat}", ""] + table(by_cat[cat], repo) + [""]
    if None in by_cat:
        lines += ["### Uncategorized", ""] + table(by_cat[None], repo) + [""]

    if deprecated:
        lines += ["### Deprecated", "",
                  "Still built and drift-checked, but no longer recommended.", ""]
        lines += table(sorted(deprecated, key=lambda p: p.name), repo) + [""]

    return "\n".join(lines).rstrip() + "\n"


def splice(readme: str, block: str) -> str:
    if BEGIN not in readme or END not in readme:
        raise SystemExit(
            f"render_index: README.md is missing the {BEGIN} / {END} markers")
    head, rest = readme.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    return f"{head}{BEGIN}\n{block}{END}{tail}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--readme", type=Path, default=Path("README.md"))
    ap.add_argument("--repo", default="krelinga/3d", help="owner/name for release links")
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if the block is out of date; write nothing")
    args = ap.parse_args()

    parts = load_or_die()
    current = args.readme.read_text()
    updated = splice(current, render(parts, args.repo))

    if args.check:
        if updated != current:
            print("render_index: README index block is out of date -- "
                  "run `make index` and commit the result", file=sys.stderr)
            return 1
        print("README index is up to date")
        return 0

    if updated != current:
        args.readme.write_text(updated)
        print(f"render_index: rewrote the index block in {args.readme}")
    else:
        print("render_index: index already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
