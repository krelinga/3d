# Previewing rendered output from the devcontainer

Status: draft — exploring options, nothing settled
Scope: how someone editing `.scad` in the devcontainer sees the resulting
geometry, on a fast enough loop to iterate against.

## Why this is its own problem

[openscad-image.md](openscad-image.md) dropped `Antyos.openscad` because its
only real value was live preview, and no GUI application can reach the
user's screen from a headless container. That was the right call, but it
left a real gap: **nothing currently closes the edit → look loop.**

[initial-design.md](initial-design.md) does specify previews — committed
`preview/<part>/<variant>.png`, fixed camera, freshness-checked by CI — but
those exist to serve a *different* job, and conflating the two jobs is what
makes this question confusing:

| | **Review** (already designed) | **Iteration** (this doc) |
|---|---|---|
| Question it answers | "should this change ship?" | "did my edit do what I meant?" |
| Audience | PR reviewer, later | the author, right now |
| Wants | stable, fixed camera, committed, diffable | fast, interactive, disposable |
| Cadence | once per PR | every few seconds |

They can share machinery, but they should not be assumed to be the same
feature. A fixed camera is a *feature* for review — initial-design.md is
explicit that reframing hides the change being reviewed — and a
*limitation* for iteration, where you often need to rotate to see the side
that matters.

## Part 1: the re-render loop

The node-style watcher pattern works here, and the environment assumptions
it depends on are confirmed rather than assumed.

**Watching the workspace works.** Verified with Node's `fs.watch` on
`scad/bases`: an in-place append fired `change`, and an atomic-rename save
(the pattern many editors use) fired `rename`. Recursive watching works.

The reason this is reliable — worth stating, because bind-mount inotify
propagation is notoriously flaky in other setups — is that **VS Code Server
runs inside the container.** Saves are therefore in-container writes, seen
natively by the container's own kernel. There's no host→container event
propagation in the path at all, which is the part that breaks on macOS and
Windows Docker Desktop setups.

**Debounce is required, not optional.** The single atomic-rename save above
produced *two* events. A trailing debounce (~100–200 ms) is the minimum;
without it a render fires mid-save against a half-written file.

**The watcher should trigger, not think.** It should run `make` (or
`make preview`) and let make's dependency graph decide what actually needs
rebuilding, rather than mapping changed-file → part itself. This reuses the
`openscad -d` dependency files initial-design.md already specifies, and it
gets the `lib/` fanout case right for free — a shared-module edit that
touches twelve parts is exactly the case a hand-rolled watcher would get
wrong. It also means the watch loop and a manual `make` do identical work,
so there's no second code path to keep honest.

Note the known gaps initial-design.md documents in those dep files
(`params.json`, `entry.yaml`, and the toolchain image are not recorded by
`openscad -d`); the watcher inherits those gaps rather than fixing them, and
should watch those paths explicitly.

**Speed is not a concern.** Measured through `bin/openscad`, a full
fixed-camera 800×600 PNG preview of `scad/bases/one_inch.scad` took
**0.35 s**, of which ~0.20 s is `docker run` startup. That is comfortably
inside "feels instant" for a save-triggered loop, and it independently
confirms openscad-image.md's estimate that per-invocation container startup
would be minor. Caveat: that is a trivial part. Boolean-heavy models will be
dominated by actual render time, not by the loop.

**Where it runs: the devcontainer side, invoking `bin/openscad` per render.**
This keeps one entry point to the toolchain rather than introducing a second
mechanism. *Rejected alternative:* a long-lived container running the
toolchain image with the watcher inside it. It would amortize the 0.2 s
startup, but that 0.2 s is not a problem worth solving, and it would need
its own lifecycle management (start, restart-on-crash, stop) plus a second
way of reaching the pinned image — against openscad-image.md's whole
premise that there is exactly one.

**What to write it in: Node, already present** (v24, verified) with
`fs.watch` built in — no new install. `inotify-tools` is available via apt
but would mean reintroducing a container install step immediately after
openscad-image.md deleted the last one.

## Part 2: how you actually see it

Four routes, roughly in increasing order of cost.

### A. PNG into a VS Code image tab

Watcher regenerates the PNG; VS Code shows it in an ordinary editor tab.
No extension, no server, nothing to maintain.

The render path is already confirmed working headlessly through the shim
(the 0.35 s measurement above *is* this path). The strongest argument for
it: what you look at while iterating is **the same artifact, from the same
command, that gets committed and diffed in the PR** — the local loop and
the CI freshness check exercise one code path, so neither can quietly rot.

Limits: static, and stuck on `entry.yaml`'s fixed camera. You cannot rotate
to inspect the back of the part, which is a real constraint for anything
with meaningful geometry facing away from the camera.

**Needs confirming:** whether VS Code's image preview auto-refreshes when
the file changes on disk. Believed yes, and cheap to check in the UI — but
the entire value of this option depends on it, so it should be verified
before building on it.

### B. STL/3MF + a webview 3D viewer extension

Several exist ([STL Previewer](https://github.com/misiekhardcore/stl-previewer),
[3D Viewer for VSCode](https://marketplace.visualstudio.com/items?itemName=slevesque.vscode-3dviewer),
[3D Model Viewer](https://marketplace.visualstudio.com/items?itemName=planetsensorllc.stl-viewer)),
all three.js-based, giving real rotate/zoom.

**The Antyos failure mode does not recur here, and it's worth being precise
about why.** `Antyos.openscad` spawned a *native Qt process inside the
container*, which needed an X display there — hence
`qt.qpa.xcb: could not connect to display`. A webview extension is
structurally different: the extension host runs in the container, but the
webview itself renders in the **local** VS Code UI process using the local
machine's GPU, with VS Code proxying the mesh data out. Nothing needs a
display inside the container.

Costs: it reintroduces a third-party extension dependency immediately after
removing one, and these extensions vary in maintenance. The crux unknown is
**auto-reload** — a custom editor/webview does not necessarily watch its
file for changes, so the watch loop might still require manually closing and
reopening the tab, which would defeat most of the point.

### C. Local web server + port forwarding

A small server on the devcontainer side (Node is already there), viewed
either in VS Code's built-in Simple Browser tab or in a real browser on the
workstation via VS Code's automatic port forwarding.

This is the only option that buys full control: an interactive viewer, live
reload pushed over SSE/WebSocket the instant a render finishes, several
variants side by side, and a real browser window that's bigger and better
accelerated than a VS Code tab.

It is also by far the most code to write and then own — a server, a client
viewer, and a reload channel — for something the first two options may
already cover. Worth building only if A and B both fall short.

One constraint if it happens: **run the server on the devcontainer side, not
inside the toolchain image.** A server inside the toolchain container would
need its port published to the devcontainer and then forwarded again, and
the toolchain image is deliberately a stateless one-shot command runner, not
a service host.

### D. Escape hatch: OpenSCAD natively on the workstation

For a local (non-Codespaces) devcontainer, `/workspaces/3d` is a bind mount
of a directory on the user's own machine. Nothing stops running a real
OpenSCAD GUI there, pointed at the same files, with its own "Automatic
Reload and Preview" — which is the best interactive experience available, by
a wide margin, and requires building nothing.

The honest caveat: that OpenSCAD is whatever version the workstation has,
**not** the pinned digest. What you see could differ from what CI builds,
which is precisely the drift the pinning exists to prevent. That is probably
fine for "am I sketching the right shape" and not fine for "is this ready to
tag" — but the distinction has to be held in the user's head, which is
exactly the kind of thing that eventually bites. Worth naming as a real
option rather than pretending the container is the only way to look at a
model.

## Recommendation

Start with **A**, escalate only if it disappoints.

It's nearly free, it reuses `make preview` which has to exist anyway for
CI, and its output is identical to the reviewed artifact — a property none
of the others have. The likely failure mode is the fixed camera rather than
the loop mechanics, and that failure will be obvious quickly.

If A proves too limited, **B** is the next-cheapest step and its one open
question (auto-reload) is answerable in an afternoon. **C** should wait
until there's concrete evidence B can't do the job. **D** is worth knowing
about regardless — it costs nothing to keep in the back pocket, as long as
its version-drift caveat stays understood.

## Open questions

- **Where do iteration renders go?** Writing to the committed
  `preview/<part>/<variant>.png` path means the working tree is dirty the
  entire time you're iterating; a gitignored scratch location avoids the
  churn but gives up option A's main advantage (that you're looking at the
  exact artifact CI checks). Genuine tension, unresolved.
- **Does VS Code's image preview auto-refresh on disk change?** Option A
  depends entirely on it.
- **Do any of the webview 3D viewers auto-reload on file change?** Option B
  depends entirely on it.
- Whether the watcher should render *all* affected parts or only the one
  being edited — delegating to `make` gets correctness right, but a `lib/`
  edit rebuilding twelve parts mid-iteration may be slower than wanted.
- Whether iteration should render PNG (cheap, matches review) or 3MF/STL
  (needed by B, and by anything interactive), or both.

## Current-state caveat

Like the rest of `docs/design/`, this describes a target that partly rests
on unbuilt work: `parts/`, `lib/`, `tools/`, and the `Makefile` do not
exist yet, so "the watcher runs `make`" has nothing to call today. The repo
is currently flat `scad/<category>/*.scad`.

An interim version is still possible and cheap — watch `scad/**/*.scad` and
invoke `bin/openscad` directly per changed file, no make involved — and it
would answer the two "needs confirming" questions above without waiting for
the build system. That's probably the right first move regardless of which
viewing option wins.
