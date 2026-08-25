#!/usr/bin/env python3
"""Verify that every string a part draws actually renders in the font it asks for.

OpenSCAD resolves an unavailable font to the default, exits 0, and writes a
perfectly valid mesh. Nothing else in this repo catches that: the catalog is
still valid, `tools/metrics.py`'s assertions still pass, and drift stays quiet
unless the substitution happens to move the measured geometry. See
docs/design/fonts.md.

Stage 1 asks OpenSCAD which (text, font) pairs a part actually draws, by
reading the evaluated CSG tree rather than parsing the source. That gets
variables, expressions, functions and module parameters right, and reports only
geometry that was actually instantiated.

Runs inside the pinned toolchain image -- invoke through bin/python3.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import Part, Variant, load_or_die, resolve  # noqa: E402

# Plain `openscad`, not `bin/openscad`. This module runs *inside* the pinned
# image (see the note above), where openscad is on PATH; bin/openscad is the
# shim that gets you into the image from outside, and it needs a docker binary
# the container does not have.
OPENSCAD = "openscad"


@dataclass(frozen=True)
class Usage:
    """One `text()` call as OpenSCAD evaluated it.

    `text` and `font` are kept in their CSG-escaped form so they can be pasted
    straight back into a probe `.scad` without an unescape/re-escape round trip
    that could change what is being tested.
    """
    text: str
    font: str
    part: str
    variant: str
    # True when CSG export produced a string this tool cannot recover -- see
    # _string_args. The usage is reported as unverifiable rather than guessed at.
    ambiguous: bool = False

    @property
    def display_text(self) -> str:
        return unescape(self.text)

    @property
    def display_font(self) -> str:
        return unescape(self.font)


def unescape(raw: str) -> str:
    """CSG string escaping -> the characters it denotes. Display only."""
    out, i = [], 0
    while i < len(raw):
        c = raw[i]
        if c == "\\" and i + 1 < len(raw):
            nxt = raw[i + 1]
            out.append({"n": "\n", "t": "\t", "r": "\r",
                        '"': '"', "\\": "\\"}.get(nxt, nxt))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _split_call(csg: str, open_paren: int) -> tuple[str, int]:
    """Return the body of a call whose '(' is at open_paren, and the index after ')'.

    Scans rather than regexes because a ')' inside a quoted string -- entirely
    legal in the text being drawn -- would end the match early.
    """
    depth, i, in_str, esc = 0, open_paren, False, False
    while i < len(csg):
        c = csg[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return csg[open_paren + 1:i], i + 1
        i += 1
    raise ValueError("unterminated call in CSG output")


def _string_args(body: str) -> tuple[dict[str, str], bool]:
    """(name -> raw string value, ambiguous?) for a call's string arguments.

    Values keep their CSG escaping verbatim, so they can be written straight
    back into a probe `.scad` without a decode/encode round trip.

    CSG export does not escape quotes inside strings: text("a \"b\"") comes back
    as `text = "a "b""`, which cannot be recovered unambiguously. That is
    detectable -- a well-formed value is followed by ',' or ')' -- and detected
    rather than silently truncated, because testing a string the part does not
    actually draw is the exact failure this tool exists to catch.
    """
    args: dict[str, str] = {}
    ambiguous = False
    i, n = 0, len(body)
    while i < n:
        if not (body[i].isalpha() or body[i] in "_$"):
            i += 1
            continue
        start = i
        while i < n and (body[i].isalnum() or body[i] in "_$"):
            i += 1
        name = body[start:i]

        while i < n and body[i] in " \t":
            i += 1
        if i >= n or body[i] != "=":
            continue
        i += 1
        while i < n and body[i] in " \t":
            i += 1
        if i >= n or body[i] != '"':
            continue

        i += 1
        buf, esc = [], False
        while i < n:
            c = body[i]
            if esc:
                buf.append(c)          # keep the escape sequence intact
                esc = False
            elif c == "\\":
                buf.append(c)
                esc = True
            elif c == '"':
                break
            else:
                buf.append(c)
            i += 1
        args[name] = "".join(buf)
        i += 1
        j = i
        while j < n and body[j] in " \t":
            j += 1
        if j < n and body[j] not in ",)":
            ambiguous = True
    return args, ambiguous


def parse_usages(csg: str, part: str, variant: str) -> list[Usage]:
    """Every text() call in an evaluated CSG tree."""
    usages: list[Usage] = []
    i = 0
    while True:
        at = csg.find("text(", i)
        if at == -1:
            break
        # "text(" also appears as the argument name `text = "..."`; require the
        # call to start at a token boundary.
        if at > 0 and (csg[at - 1].isalnum() or csg[at - 1] in "_$"):
            i = at + 5
            continue
        body, after = _split_call(csg, at + 4)
        args, ambiguous = _string_args(body)
        usages.append(Usage(text=args.get("text", ""), font=args.get("font", ""),
                            part=part, variant=variant, ambiguous=ambiguous))
        i = after
    return usages


def export_csg(part: Part, variant: Variant) -> str:
    """The evaluated CSG tree for one part/variant."""
    cmd = [OPENSCAD, "--export-format", "csg", "-o", "-"]
    if variant.param_set is not None:
        cmd += ["-p", str(part.params), "-P", variant.param_set]
    cmd += [str(part.source)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(
            f"check_fonts: CSG export failed for {part.name}/{variant.name}:\n"
            + (proc.stderr or "").strip())
    return proc.stdout


def usages_for(part: Part) -> list[Usage]:
    found: list[Usage] = []
    for variant in part.variants:
        found += parse_usages(export_csg(part, variant), part.name, variant.name)
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", help="check one part instead of all of them")
    ap.add_argument("--show-usages", action="store_true",
                    help="list the (text, font) pairs found and stop")
    args = ap.parse_args()

    parts = [resolve(args.part)] if args.part else load_or_die()

    usages: list[Usage] = []
    for part in sorted(parts, key=lambda p: p.name):
        usages += usages_for(part)

    if args.show_usages:
        if not usages:
            print("no text() calls in any part")
            return 0
        for u in usages:
            where = f"{u.part}/{u.variant}"
            print(f"  {where:40s} text={u.display_text!r:20s} "
                  f"font={u.display_font!r}")
        return 0

    print(f"check_fonts: found {len(usages)} text() call(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
