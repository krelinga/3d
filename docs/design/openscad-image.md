# Toolchain image in the devcontainer

Status: draft — actively being iterated on, unlike `initial-design.md`
Scope: how local development (the devcontainer) gets access to the pinned
`openscad-build` toolchain image, now that making it the devcontainer's base
image directly has been tried and reverted.

## Background

`initial-design.md` calls for the toolchain to be "pinned by
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
`initial-design.md` originally assumed.

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

### `PATH` inside the devcontainer — confirmed, via `/usr/local/bin` symlinks

The devcontainer has three distinct consumers that need `openscad` on
`PATH`, with different propagation guarantees under `devcontainer.json`'s
own env mechanisms: the VS Code extension host (what `remoteEnv` actually
scopes to), Claude Code (also installed as a devcontainer feature, running
its own tool calls), and plain interactive/exec shells. Rather than reason
through which hook covers which consumer, the shims get symlinked into
`/usr/local/bin`, which is on the OS-level default `PATH` for any process
in the container regardless of how it was launched — and, being ahead of
`/usr/bin` in Debian/Ubuntu's default ordering, would take precedence over
any stray natively-installed `openscad` too.

Mechanism: `postCreateCommand` loops over the symlinks checked into `bin/`
(skipping the real `.toolchain-shim` file, which is dot-prefixed and so
excluded by a plain `bin/*` glob) and runs
`sudo ln -sf "${containerWorkspaceFolder}/bin/<name>" "/usr/local/bin/<name>"`
for each. A new shimmed command then only needs a new symlink added under
`bin/` — no `devcontainer.json` edit.

**`setup.sh` goes away entirely, rather than being repurposed for this.**
Its only job was apt-installing stable OpenSCAD, which this whole
direction is meant to make unnecessary — the devcontainer no longer needs
OpenSCAD installed natively at all, only the shims. The symlink loop above
is small enough to live inline as `postCreateCommand`'s value directly in
`devcontainer.json`; keeping a separate script file around for it would be
one more place to look for no real benefit.

Verified from inside the actual devcontainer with a throwaway shim +
symlink standing in for the real ones: `/usr/local/bin` does precede
`/usr/bin` in this devcontainer's actual `PATH`; `sudo ln -sf` works with
the `vscode` user's existing passwordless sudo; and a double-symlink chain
(`/usr/local/bin/<name>` → `bin/<name>` → `bin/.toolchain-shim`) resolves
correctly by bare name from an unrelated `cwd`, with `basename "$0"`
inside the shim correctly reporting the invoked name rather than the
underlying script's filename — the part the `argv[0]`-dispatch trick
depends on. Ran as the normal `vscode` uid/gid throughout, not root.

Not independently verified: `${containerWorkspaceFolder}` substitution
itself, since that's resolved by the devcontainer CLI / VS Code's Dev
Containers extension at `postCreateCommand` time, not reproducible from a
plain shell without an actual container rebuild. The test above used the
real absolute path (`/workspaces/3d`) as a stand-in for what that
documented, standard devcontainer variable resolves to.

### `PATH` in GitHub Actions — confirmed usable, and simpler than the devcontainer case

The reason the devcontainer needs the `/usr/local/bin` workaround at all is
that it has multiple distinct consumer processes with different `PATH`
propagation guarantees. A GitHub Actions job doesn't have that problem —
it's sequential `run:` steps sharing state through `$GITHUB_PATH`, which is
the built-in mechanism for exactly this: one step does
`echo "$GITHUB_WORKSPACE/bin" >> "$GITHUB_PATH"` and every later step in
that job gets it prepended, no `sudo`, no symlinks, no rebuild-time
variable substitution involved.

Everything else about the design carries over to GitHub Actions
unmodified:

- GitHub-hosted `ubuntu-latest` runners are bare VMs, not containers, so
  there's no nested-Docker-in-Docker complexity — `docker run` talks to an
  already-running daemon directly.
- The default `runner` user is already in the `docker` group (same as
  `vscode` is here), so `docker run` needs no `sudo` there either.
- `run:` steps default to `cwd = $GITHUB_WORKSPACE`, so
  `-v "$PWD:/work" -w /work` behaves identically to local use.
- `--user "$(id -u):$(id -g)"` needs no special-casing — same fix, same
  reason, in both places.
- `bin/openscad`'s symlink-ness and executable bit both survive
  `actions/checkout` on Linux runners — git tracks both natively.
- The image is public, so pulling it needs no `docker login` in CI (only
  `image.yml`'s *push* step needs auth) — already confirmed by pulling it
  anonymously earlier in this investigation.

So the same `bin/.toolchain-shim` script is usable unmodified in both
environments; only the "how does `bin/` get onto `PATH`" step differs
(`$GITHUB_PATH` in CI vs. the `/usr/local/bin` symlink dance locally).

## `Antyos.openscad`: dropped, not fixed

Rebuilding the devcontainer and trying the extension surfaced two problems,
neither of which is fixable within this design:

- **"Preview in OpenSCAD"** shells out to `openscad` with no `-o`, to
  launch the actual GUI application and leave it open (relying on
  OpenSCAD's own "Automatic Reload and Preview" for live updates). That
  needs a real Qt platform plugin backed by a real display —
  `qt.qpa.xcb: could not connect to display` is Qt failing to find one.
  This isn't specific to the shim: it would fail identically with a
  natively-installed OpenSCAD in this same headless devcontainer, since
  there's no X server here and no display-forwarding setup at all. No
  wrapper design fixes a missing display.
- **"Export Model"**, the one command that *is* a plain headless `-o`
  invocation (the shape this whole design targets, and the one already
  confirmed working directly via `bin/openscad`), still failed — it
  passes absolute paths for input/output, and the shim mounts `$PWD` at
  `/work` rather than at the same absolute path, so an argument like
  `/workspaces/3d/scad/...` doesn't resolve inside the container even
  though it's technically under `$PWD`. Fixable in principle
  (`-v "$PWD:$PWD" -w "$PWD"` instead of remapping to `/work`), but not
  worth doing for this extension specifically — see below.

Stepping back, the extension's only real value to this repo was the live
preview, and that was never going to work here regardless of these bugs —
this is a headless devcontainer with no path for a GUI window to reach the
user's actual screen, which no VS Code extension can paper over.
`initial-design.md`'s actual answer to "what does this part look like" is
unrelated to any of this anyway: committed `preview/<part>/<variant>.png`
files, generated by `make preview`, reviewed via GitHub's image diff in a
PR — not a live in-editor preview. So dropping the extension isn't a gap
against the target design, it's just not fighting a tool that was never
going to serve it. Removed from `devcontainer.json`'s extensions list.

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
