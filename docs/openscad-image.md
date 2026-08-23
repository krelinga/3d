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

- **File ownership — confirmed both the problem and the fix.** A plain
  `docker run` writing into the bind-mounted workspace comes back
  `root:root`-owned, as expected (reproduced with the same `alpine:3` test
  used for the mount-semantics check above) — not something the `vscode`
  user can clean up without `sudo`. Adding `--user "$(id -u):$(id -g)"`
  fixes it: the same write comes back owned by `vscode:vscode` and is
  removable without `sudo`. Whatever wrapper we write needs this built in,
  not left as a thing people rediscover the hard way.

- **Docker-in-Docker mount semantics — confirmed working.** Docker-in-Docker
  runs a real nested `dockerd` (verified: a `dockerd` process running inside
  the devcontainer itself, `docker info` reporting `Operating System: Ubuntu
  24.04.3 LTS (containerized)`, hostname matching the devcontainer's own
  container ID — this is the nested daemon, not a host-socket passthrough).
  Tested a full round trip from inside the devcontainer: wrote a marker file
  into the workspace, bind-mounted `$PWD` into a plain `alpine:3` container
  run against the nested daemon, read the marker back correctly inside the
  container, wrote a new file from inside the container, and confirmed it
  appeared back in the workspace on the host side. The nested daemon shares
  the devcontainer's filesystem view, as assumed — `-v "$PWD:/work"` works
  exactly as it would against a non-nested daemon.

- **One generic wrapper, not one script per command.** The Makefile and
  `tools/*.py` layer initial-design.md describes will eventually want to run
  *entirely* inside this container — not just `openscad` itself, but the
  Python metrics/catalog tooling too. A pile of one-off scripts
  (`render.sh`, `preview.sh`, ...) each hardcoding their own `docker run`
  invocation is plumbing we'd likely redo at that point. See "Where the
  wrapper lives" below for the concrete shape.

- **`openscad` needs to exist as a real executable on `PATH`.** The
  `Antyos.openscad` VS Code extension shells out to a local `openscad`
  binary for in-editor preview/validation — confirmed, not just a
  build-time concern. The generic wrapper above isn't enough by itself; the
  extension needs to be able to call `openscad` exactly as if it were
  installed natively. See below.

- **Per-invocation startup overhead is expected to be minor.** Each call
  pays container-startup cost, but the image is already pulled/cached
  locally, so this should be sub-second — not a concern for interactive use,
  only worth revisiting if something ends up invoking it in a tight
  per-file loop.

## Where the wrapper lives, and how CI reaches the same image

**Location: repo-root `bin/`, not `.devcontainer/`.** The wrapper's actual
mechanism — `docker run` against whatever daemon `docker` is configured to
talk to — isn't inherently devcontainer-specific; Docker-in-Docker is just
how *this* devcontainer happens to supply a daemon. It also needs to stay
separate from `tools/` in the target design: `tools/*.py` runs *inside* the
pinned container, while this wrapper is what gets you *into* it — mixing
the two in one directory would blur that distinction.

**Interface: one real script, dispatched by `argv[0]`.** `bin/.toolchain-shim`
is the only real logic:

```sh
#!/bin/sh
set -e
IMAGE="ghcr.io/krelinga/3d/openscad-build@sha256:dff4de91db7808c0b48439af71e582e44e46daf3ec9ea477b86b95d2d5c8ef43"
exec docker run --rm -v "$PWD:/work" -w /work --user "$(id -u):$(id -g)" \
  "$IMAGE" "$(basename "$0")" "$@"
```

`bin/openscad` is a symlink to it. Adding the next shimmed command
(`python3` for the metrics tooling, `convert` for preview checks) is then
"add one symlink," not "write and maintain a second near-identical script."

**`IMAGE` lives only in this one script — including for CI.** The original
idea (a shared `.devcontainer/toolchain-image` file, read separately by the
shim and by each workflow's `container:` key) doesn't actually work as
cleanly as it sounds: GitHub Actions' job-level `container:` can only be
built from expressions over the `github`, `needs`, `vars`, `matrix`, and
`inputs` contexts — it cannot read an arbitrary checked-in file. The
practical ways to feed it a shared value would be a GitHub Actions repo
*variable* (lives in repository settings, not git — no diff, no blame, no
review trail, which cuts against how deliberately this repo treats
digest-pinning as an in-repo, reviewable fact) or a `needs:`-chained setup
job that reads the file and republishes it as a job output (works, but is
real ceremony, repeated — or centralized and depended on — by every
workflow that needs it).

Routing CI through the same shim sidesteps the problem entirely: future
`pr.yml` / `main.yml` / `release.yml` add `bin/` to `PATH`
(`echo "$GITHUB_WORKSPACE/bin" >> "$GITHUB_PATH"`) and call `openscad` (and
friends) exactly as steps written for `container:` would have. The digest
then has exactly one home, rather than being duplicated — and therefore
driftable — across `devcontainer.json` and three workflow files the way
`docs/design/initial-design.md` originally assumed.

**This is a deliberate divergence from `initial-design.md`'s CI section**,
which says "All workflows run in the pinned image via `container:`."
Trade-off, considered and accepted: `container:` amortizes container
startup once per job; per-step `docker run` via the shim pays that cost on
every invocation instead. On GitHub-hosted runners this should be a
non-issue in practice — they're bare VMs, not themselves containers, so
(unlike our devcontainer) there's no nested-Docker-in-Docker problem, and
`docker run` overhead against an already-pulled image is well under a
second — almost certainly noise next to actual OpenSCAD render time across
a part/variant matrix. `initial-design.md` should be updated to describe
this instead of `container:` once it's implemented, rather than left
describing an approach that's no longer the plan.

## Open questions

- How the `openscad` shim gets onto `PATH` inside the devcontainer — a
  `remoteEnv`/`containerEnv` `PATH` addition in `devcontainer.json`
  pointing at `bin/`, most likely, but not yet written.
- Whether `Antyos.openscad` shells out to anything besides `openscad`
  itself that would also need a shim.
- Whether `setup.sh` is still the right place for whatever install step
  remains (currently: apt-installing stable OpenSCAD, which this direction
  is meant to make unnecessary — the devcontainer would no longer need
  OpenSCAD installed natively at all, only the shim).
- Update `initial-design.md`'s CI section to describe the shim-based
  approach instead of `container:`, once this is actually implemented.

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
