# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A collection of OpenSCAD (`.scad`) source files for 3D-printable parts. Mesh
files (STL/3MF) are treated as build output, not source — they are not
committed.

## Current state vs. target design

**The repo today is a small, flat collection**: `.scad` files live directly
under `scad/<category>/`, and `generate.sh` renders each one by hand to STL
with a hardcoded output path (`/nas/dev/3d/stl/...`) and no parameters,
variants, or CI.

**`docs/design/initial-design.md` describes a target architecture that has not
been built yet.** It specifies a `parts/` monorepo layout (one directory per
part, `entry.yaml` + `source.scad` + optional `params.json`), a `lib/` for
shared OpenSCAD modules (including a BOSL2 submodule), a generated Makefile,
and three GitHub Actions workflows (PR build, main-branch drift detection,
on-demand per-part release) built on a toolchain image pinned by digest.
**None of `parts/`, `lib/`, `tools/`, the Makefile, or the workflows exist
yet.** Before assuming any command, file, or convention described in the
design doc is available, check whether it has actually been implemented —
read the design doc in full for the target shape, but verify against the
current tree before relying on it.

When implementing pieces of this design, follow the doc closely: it documents
not just the target state but the rejected alternatives and the reasoning
behind each decision (e.g. why parts are named by leaf directory rather than
full path, why 3MF is the single rendered format with STL derived from it,
why geometry comparisons are tolerance-based rather than byte/hash-based, why
drift detection runs after merge rather than blocking the PR). Re-read the
relevant section rather than re-deriving the design from scratch.

## Commands

Rendering a part to STL, current (manual) style, matching `generate.sh`:

```sh
openscad -o <output>.stl scad/<category>/<part>.scad
```

`generate.sh` is a one-off script hardcoded to a personal `/nas/dev/3d`
output path — it is not a general-purpose build tool and will not work
unmodified for anyone else.

There is no test suite, linter, or CI configured yet.

## Environment

The devcontainer (`.devcontainer/devcontainer.json`) provides Ubuntu Noble
with `openscad` (installed via `.devcontainer/setup.sh`), Node.js LTS,
Claude Code, and Docker-in-Docker. The `Antyos.openscad` VS Code extension is
configured for `.scad` editing.

Note: the devcontainer setup does **not** currently match the design doc's
"pinned dev-snapshot image digest" requirement — it installs `openscad` from
`apt`, which is the stable 2021.01 release, not the dev snapshot the design
doc says every feature it relies on requires (`--backend=manifold`,
`--hardwarnings`, `--check-parameter-ranges`, headless EGL PNG export). If
implementing the design's build/CI pipeline, the toolchain image work
(`image.yml`, `.devcontainer/Dockerfile`, digest pinning) needs to happen
first.

## Key design principles (from `docs/design/initial-design.md`)

These matter for any future work extending this repo, not just literal
implementation of the design doc:

- **Directory listing as catalog.** Whatever organizes parts should avoid
  declaring a part's identity in more than one place (e.g. don't add a
  central manifest that duplicates directory names).
- **Measure geometry, don't hash it.** OpenSCAD output is not
  byte-reproducible run-to-run (upstream issue #4931) or across lib3mf
  versions (#5800). Any comparison of build output must be tolerance-based
  (bbox/volume/area) rather than checksum-based.
- **Pin the toolchain by image digest, everywhere it's used**, not by a
  version string — there's no current OpenSCAD stable release with the
  needed features.
