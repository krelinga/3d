# Toolchain image in the devcontainer

Status: draft — actively being iterated on, unlike `design/initial-design.md`
Scope: how local development (the devcontainer) gets access to the pinned
`openscad-build` toolchain image, now that making it the devcontainer's base
image directly has been tried and reverted.

## Background

`docs/design/initial-design.md` calls for the toolchain to be "pinned by
image digest, in every place that builds" — explicitly including the
devcontainer, "so local and CI builds are the same claim rather than two
similar ones."

The straightforward reading of that — point `devcontainer.json`'s `image` at
the same digest CI publishes — was tried:

1. `0ee2606` / `fea9638` / `c4354da` built `.devcontainer/Dockerfile`
   (`FROM openscad/openscad:dev.2026-01-12`, plus `python3-trimesh`,
   `python3-yaml`, `imagemagick`) and `.github/workflows/image.yml` to build
   and publish it to `ghcr.io/krelinga/3d/openscad-build`.
2. `4a9333a` pointed `devcontainer.json`'s `image` at the published digest
   and dropped `setup.sh` (its only job, apt-installing OpenSCAD, was now
   baked into the image).
3. That broke: `ghcr.io/devcontainers/features/docker-in-docker:2` does not
   support the base OS the image inherits from
   `openscad/openscad:dev.2026-01-12` — Debian 13 ("trixie"), not Ubuntu.
   Reverted in `851f5c7`, merged as `2310e9b`.

**Current state**, as a result: `devcontainer.json` is back to
`mcr.microsoft.com/devcontainers/base:noble` with `setup.sh` apt-installing
stable OpenSCAD 2021.01 — the same drift `CLAUDE.md` and initial-design.md's
"Current state vs. target design" already flag (no `--backend=manifold`, no
headless EGL preview rendering, a different toolchain than CI uses). This doc
is about closing that gap without repeating the base-image approach that just
failed.

## Direction: invoke the toolchain image, don't boot from it

Rather than making `openscad-build` the devcontainer's base image, keep the
devcontainer on the Ubuntu base — where `node`, `claude-code`, and
`docker-in-docker` are all known to work — and reach the toolchain by running
it as a container, via Docker-in-Docker, from inside the devcontainer:

```sh
docker run --rm -v "$PWD:/work" -w /work \
  ghcr.io/krelinga/3d/openscad-build@sha256:<digest> \
  openscad ...
```

This keeps the "one digest, referenced everywhere" property intact — local
dev and CI both execute commands inside the identical pinned container, just
through a different mechanism (`docker run` locally vs. GitHub Actions'
`container:` key in CI) rather than through a shared devcontainer base image.

## Requirements this needs to satisfy

- **File ownership.** The toolchain image likely runs as root by default, so
  anything a naive `docker run` writes back into the bind-mounted workspace
  (`.stl`/`.3mf`/preview PNGs) comes back root-owned, which breaks the
  non-root `vscode` user's ability to touch its own output. Whatever wrapper
  we write needs `--user "$(id -u):$(id -g)"` (or equivalent) built in, not
  left as a thing people rediscover the hard way.

- **Docker-in-Docker mount semantics need to be verified, not assumed.**
  Docker-in-Docker runs a real nested `dockerd`. Whether a bind mount like
  `-v "$PWD:/work"`, issued from inside the devcontainer against that nested
  daemon, actually resolves to the expected files depends on the nested
  daemon sharing the same filesystem view as the devcontainer shell. That's
  usually true for this devcontainer feature, but it's an assumption, and
  it's cheap to prove with one throwaway `docker run` before writing anything
  that depends on it. **Not yet tested.**

- **One generic wrapper, not one script per command.** The Makefile and
  `tools/*.py` layer initial-design.md describes will eventually want to run
  *entirely* inside this container — not just `openscad` itself, but the
  Python metrics/catalog tooling too. A pile of one-off scripts
  (`render.sh`, `preview.sh`, ...) each hardcoding their own `docker run`
  invocation is plumbing we'd likely redo at that point. A single generic
  wrapper that runs an arbitrary command inside the pinned image (e.g.
  `tools/toolchain <cmd...>` → `docker run ... "$@"`) gives that future layer
  one thing to shell out through instead of N scripts to keep in sync.

- **`openscad` needs to exist as a real executable on `PATH`.** The
  `Antyos.openscad` VS Code extension shells out to a local `openscad`
  binary for in-editor preview/validation — confirmed, not just a
  build-time concern. The generic wrapper above isn't enough by itself; we
  also need a thin `openscad`-named shim on `PATH` inside the devcontainer
  that forwards to the same `docker run` invocation
  (`openscad "$@"` → `tools/toolchain openscad "$@"`, or equivalent), so the
  extension can call it exactly as if it were installed natively.

- **Per-invocation startup overhead is expected to be minor.** Each call
  pays container-startup cost, but the image is already pulled/cached
  locally, so this should be sub-second — not a concern for interactive use,
  only worth revisiting if something ends up invoking it in a tight
  per-file loop.

## Open questions

- Confirm the Docker-in-Docker mount-semantics assumption above with an
  actual test, before building anything on top of it.
- Where the generic wrapper lives and its exact interface (working
  directory handling, how it locates the pinned digest — read from
  `devcontainer.json`? a shared file both it and CI read from?).
- How the `openscad` shim gets onto `PATH` — a script checked in under
  e.g. `.devcontainer/bin/` plus a `remoteEnv`/`containerEnv` `PATH`
  addition in `devcontainer.json`, vs. some other mechanism.
- Whether `Antyos.openscad` shells out to anything besides `openscad`
  itself that would also need a shim.
- Whether `setup.sh` is still the right place for whatever install step
  remains (currently: apt-installing stable OpenSCAD, which this direction
  is meant to make unnecessary — the devcontainer would no longer need
  OpenSCAD installed natively at all, only the shim).

## Rejected alternative: toolchain image as the devcontainer's base image

Covered above under Background: tried in `4a9333a`, reverted in `851f5c7`.
The failure was concrete and not a matter of tuning — the
`docker-in-docker` devcontainer feature does not support the base OS
`openscad/openscad:dev.*` images ship (Debian trixie), and that feature is
load-bearing for this repo's devcontainer (`node`, `claude-code`, and
`docker-in-docker` are all currently installed as features on top of
whatever image `devcontainer.json` names). Swapping the toolchain image's
own base OS to something the feature supports was considered separately —
see the "third option" discussion this doc's predecessor conversation
covered — and rejected on reproducibility grounds: it would decouple the
OpenSCAD binary from the base OS the upstream project actually tests it
against, reintroducing exactly the kind of run-to-run variability
initial-design.md's digest-pinning is meant to eliminate.
