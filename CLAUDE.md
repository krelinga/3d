# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A collection of OpenSCAD (`.scad`) source files for 3D-printable parts. Mesh
files (STL/3MF) are treated as build output, not source — they are not
committed.

## Design docs — read the relevant one before building

`docs/design/` holds three docs. They document not just the target state but
the rejected alternatives and the reasoning behind each decision, and several
decisions were revised after being tested. **Re-read the relevant section
rather than re-deriving the design from scratch**, and prefer the doc's
conclusion over what seems obvious — in more than one case the obvious answer
was tried first and failed.

| Doc | Covers | Status |
|---|---|---|
| `initial-design.md` | Repo structure, catalog, versioning, build, CI, releases | Target design; largely unbuilt |
| `openscad-image.md` | How the pinned toolchain image is built and reached, locally and in CI | **Built and in use** |
| `previews.md` | Live rotatable preview loop for iterating on a model | Prototype built and validated |

They cross-reference rather than duplicate: `initial-design.md` delegates
toolchain-reachability questions to `openscad-image.md` and iteration-preview
questions to `previews.md`. When updating one, check whether a claim in
another has gone stale.

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
- **Preview server.** `viewer/server.mjs` + `viewer/index.html` — watches
  `parts/` and `lib/`, runs `make`, and pushes a reload over SSE to a three.js
  viewer that preserves the camera across re-renders.

**Not built yet** — `parts/`, `lib/`, `tools/`, the `Makefile`, the committed
`thumbnails/` PNGs, and the `pr.yml` / `main.yml` / `release.yml` workflows. The
models still live flat under `scad/<category>/*.scad`, and `generate.sh` is a
one-off hardcoded to a personal `/nas/dev/3d` path — not a general build tool
and not worth extending.

Before assuming any command, file, or convention from a design doc exists,
check the tree.

## Commands

Run OpenSCAD through the shim, which executes it inside the pinned image:

```sh
openscad --backend=manifold --hardwarnings -o out.3mf scad/bases/one_inch.scad
```

Bare `openscad` works because of the `/usr/local/bin` symlink; `./bin/openscad`
is equivalent and works regardless of `PATH`.

Live preview while editing (then open the forwarded port 5173):

```sh
node viewer/server.mjs one-inch      # --format stl|3mf, --port N
```

There is no test suite, linter, or CI beyond `image.yml` yet.

### Gotchas that have already bitten

- **Absolute paths outside the workspace don't resolve.** The shim bind-mounts
  `$PWD` at `/work`, so arguments must be repo-relative.
- **OpenSCAD infers export format from the file suffix** and hard-errors on an
  unknown one (`-o foo.stl.tmp` → *"Invalid suffix tmp"*). Temp files need a
  format-valid suffix, or an explicit `--export-format`.
- **OpenSCAD streams its output** — a render produces many incremental writes,
  so anything reading the output concurrently should read a path that was
  atomically renamed into place.
- **`--hardwarnings` is not optional** in the build: OpenSCAD otherwise exits 0
  after warning about non-manifold output.

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
