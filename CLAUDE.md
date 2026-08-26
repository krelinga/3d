# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A collection of OpenSCAD (`.scad`) source files for 3D-printable parts. Mesh
files (STL/3MF) are treated as build output, not source — they are not
committed.

## Design docs — read the relevant one before building

`docs/design/` holds four docs. They document not just the target state but
the rejected alternatives and the reasoning behind each decision, and several
decisions were revised after being tested. **Re-read the relevant section
rather than re-deriving the design from scratch**, and prefer the doc's
conclusion over what seems obvious — in more than one case the obvious answer
was tried first and failed.

| Doc | Covers | Status |
|---|---|---|
| `initial-design.md` | Repo structure, catalog, versioning, build, CI, releases | **Built and in use** |
| `openscad-image.md` | How the pinned toolchain image is built and reached, locally and in CI | **Built and in use** |
| `previews.md` | Live rotatable preview loop for iterating on a model | **Built and in use** |
| `fonts.md` | Using `text()` safely: what is pinned, and the silent-fallback hazard | **Built and in use** |

They cross-reference rather than duplicate: `initial-design.md` delegates
toolchain-reachability questions to `openscad-image.md`, iteration-preview
questions to `previews.md`, and `text()` questions to `fonts.md`. When
updating one, check whether a claim in another has gone stale.

## Current state

**Built and working:**

- **Toolchain image.** `.devcontainer/Dockerfile` (pinned
  `FROM openscad/openscad:dev.2026-01-12`, plus `python3-trimesh`,
  `python3-yaml`, `imagemagick`), published by `.github/workflows/image.yml`
  to `ghcr.io/krelinga/3d/openscad-build`.
- **`bin/` shim.** `bin/.toolchain-shim` runs a command inside the pinned
  image via `docker run`, dispatched by `argv[0]`; `bin/openscad` is a symlink
  to it. That script is the **only** operative declaration of the image digest
  (`openscad-image.md` quotes it, but only as illustration).
  `devcontainer.json`'s `postCreateCommand` symlinks the shims into
  `/usr/local/bin`, so `openscad` is on `PATH` for every process in the
  container.
- **Catalog and build.** Parts live at
  `parts/<category>/<name>/{entry.yaml,source.scad}` (7 parts across `bases/`
  and `jigs/`), with shared modules in `lib/krelinga/`. The `Makefile`
  generates its per-part rules into `build/parts.mk` via `tools/gen_rules.py`,
  so adding a part means adding a directory and nothing else. Supporting tools:
  `catalog.py` (validate), `render_index.py` (README index block),
  `metrics.py` (3MF → STL + geometry metrics), `drift.py` (built metrics vs.
  the last release), `check_fonts.py` (see below), `build_record.py` and
  `print_md.py` (release assets).
- **Committed thumbnails.** `thumbnails/<part>/<part>.png`, rendered by
  `make thumbnails`. The rules call `tools/place_thumbnail.sh` rather than
  `mv`: a fresh render replaces the committed PNG only if it differs by more
  than `THUMB_TOLERANCE_PX` (50), because the same mesh rasterizes one pixel
  differently on a different CPU. CI is then just `git diff --quiet --
  thumbnails/`, since noise never reaches the working tree in the first place.
- **Font check.** `tools/check_fonts.py` asks OpenSCAD for the evaluated CSG
  tree and measures each `(text, font)` pair against a deliberately
  unresolvable control name, catching the silent fallback that leaves a
  valid mesh and a zero exit code. Wired into `make check` and `pr.yml`.
- **CI.** `pr.yml` (catalog, fonts, build, thumbnail freshness, index, a
  metrics-diff comment, mesh artifacts), `main.yml` (check, build, then
  file/update drift issues against each part's most recent release), and
  `release.yml` (per-part tag and release), alongside `image.yml`.
- **Pre-commit hook.** `.githooks/pre-commit` runs `make check` — see Commands
  for what that does and does not cover.
- **Preview server.** `viewer/server.mjs` + `viewer/index.html` — watches
  `parts/` and `lib/`, runs `make`, and pushes a reload over SSE to a three.js
  viewer that preserves the camera across re-renders.

**Nothing from the design docs is outstanding** — all four now have an
implementation. The one real gap is coverage rather than code: no part uses
`text()` yet, so `check_fonts.py` reports `0 text() call(s)` and the check is
wired but unexercised. The first part that draws text is the one that proves
it works.

Before assuming any command, file, or convention from a design doc exists,
check the tree.

## Commands

```sh
make pr    # validate, build, regenerate thumbnails + README index; run before pushing
```

Individual targets exist (`make check`, `make index`, `make thumbnails`) but
`make pr` runs them in CI's order and regenerates rather than only checking.

A committed `pre-commit` hook (`.githooks/pre-commit`, enabled via
`core.hooksPath` in `postCreateCommand`) runs `make check` on every commit:
catalog validation, README-index freshness and font resolution, about a
second. It does not build or check thumbnails. It validates the *working
tree*, not the staged content, so a partially staged tree can produce a false
pass or fail — it is a fast first filter, not the authority. Bypass with
`git commit --no-verify`.

Run OpenSCAD directly through the shim, which executes it inside the pinned
image:

```sh
openscad --backend=manifold --hardwarnings -o out.3mf parts/bases/minibase-one-inch/source.scad
```

Bare `openscad` works because of the `/usr/local/bin` symlink; `./bin/openscad`
is equivalent and works regardless of `PATH`.

Live preview while editing (then open the forwarded port 5173):

```sh
node viewer/server.mjs minibase-one-inch      # --format stl|3mf, --port N
```

There is no test suite or linter. CI is the four workflows above; the
geometry assertions in `tools/metrics.py` are the closest thing to a test.

### Gotchas that have already bitten

- **Absolute paths outside the workspace don't resolve.** The shim bind-mounts
  `$PWD` at `/work`, so arguments must be repo-relative.
- **OpenSCAD infers export format from the file suffix** and hard-errors on an
  unknown one (`-o foo.stl.tmp` → *"Invalid suffix tmp"*). Temp files need a
  format-valid suffix, or an explicit `--export-format`.
- **OpenSCAD streams its output** — a render produces many incremental writes,
  so anything reading the output concurrently should read a path that was
  atomically renamed into place.
- **`imagemagick` / `bin/magick` are load-bearing again.** They were briefly
  not: thumbnails were compared byte-for-byte, and dropping imagemagick was a
  candidate for the next pin bump. Then a thumbnail turned out to differ
  between the devcontainer and the GitHub runner by exactly one pixel — a
  depth tie at a silhouette corner, broken differently by different CPUs — so
  `tools/place_thumbnail.sh` now measures pixels on every build. Do not remove
  imagemagick from the image. `initial-design.md`, "Why not a pixel tolerance",
  has the measurements.
- **OpenSCAD's exit code is not a sufficient gate.** An *empty* top-level
  object exits 1 (so the build stops there), but a *non-manifold* result exits
  0 with a file written, and `--hardwarnings` does not change that — measured,
  not assumed. `tools/metrics.py`'s assertions are the only thing catching
  non-manifold output, which makes them load-bearing rather than belt-and-braces.

## Environment

Ubuntu Noble devcontainer with Node LTS, Claude Code, and Docker-in-Docker.
OpenSCAD is **not** installed natively — it is reached only through the shim,
which runs the pinned image via docker-in-docker.

The devcontainer deliberately has **no OpenSCAD-related VS Code extension**.
`Antyos.openscad` was removed: its preview launches a native GUI needing an X
display the container doesn't have, and its export passes absolute paths the
shim can't resolve. `previews.md` records four 3D-viewer extensions that were
evaluated and why none worked; don't re-add one without reading that.

## Key design principles

These matter for any work extending this repo, not just literal implementation
of the design docs:

- **Directory listing as catalog.** Avoid declaring a part's identity in more
  than one place (e.g. don't add a central manifest duplicating directory
  names).
- **Measure geometry, don't hash it.** OpenSCAD output is not byte-reproducible
  run-to-run (upstream #4931) or across lib3mf versions (#5800). Compare build
  output with tolerances on bbox/volume/area, never checksums.
- **Pin the toolchain by digest, declared once.** Not by version string —
  there's no current OpenSCAD stable release with the needed features.
- **Verify before designing on top.** Several decisions here were reversed by
  actually testing them; the docs record both the failure and the correction.
