# Previewing rendered output from the devcontainer

Status: prototype built and validated; remaining work is integration with the build system
Scope: how someone editing `.scad` in the devcontainer sees the resulting
geometry, interactively and from any angle, on a fast enough loop to iterate
against.

## What this is for

[openscad-image.md](openscad-image.md) dropped `Antyos.openscad` because its
only real value was live preview, and no GUI application can reach the user's
screen from a headless container. That left the edit → look loop unclosed.

**Requirement: the preview must be rotatable.** A fixed-camera image cannot
answer "is the back of this part right," which is most of what previewing is
for. That rules out the still-image route as the primary mechanism.

**Deferred, deliberately:** the committed fixed-camera **thumbnails** that
[initial-design.md](initial-design.md) specifies for PR review are a
*different feature* answering a different question ("should this ship?", for
a reviewer, later) and are not designed here. They will likely share the
watch loop below, and that sharing is worth doing when the time comes — but
designing both at once conflates two things with opposite requirements
(disposable/interactive vs. stable/diffable).

Everything below assumes the toolchain design in
[openscad-image.md](openscad-image.md) and the build design in
[initial-design.md](initial-design.md) work as written.

## The shape

```
    you save foo.scad
           │
           ▼
    ┌─────────────┐   watches sources, debounces, decides nothing
    │   watcher   │
    └──────┬──────┘
           │ runs
           ▼
    ┌─────────────┐   decides what actually needs rebuilding
    │    make     │   (already has the dependency graph)
    └──────┬──────┘
           │ bin/openscad → temp → atomic mv
           ▼
      out/…/foo.3mf ──────────┐ served on request
           │                  │
           │ "done" (only after the file is complete)
           ▼                  ▼
    ┌──────────────────────────────┐
    │  local server  ──SSE push──▶ │  browser / Simple Browser tab
    │                              │  three.js scene stays alive;
    │                              │  only geometry is swapped
    └──────────────────────────────┘
```

**One watcher, watching sources only.** Nothing watches the output — the
reload signal is pushed after the render completes. That single change is
what removes the whole class of failure found below.

## Part 1: the loop

**The watcher detects; `make` decides.** The watcher should not map
changed-file → part. `make` already owns the dependency graph (including the
`openscad -d` files), so delegating gets `lib/` fanout right for free — a
shared-module edit touching twelve parts is exactly the case a hand-rolled
watcher gets wrong — and guarantees the loop and a manual `make` do identical
work.

The watcher inherits the dep-file gaps initial-design.md already documents
(`params.json`, `entry.yaml`, and the toolchain image are not recorded by
`openscad -d`) and should watch those paths explicitly.

**Verified facts** (measured in this devcontainer, not assumed):

| | |
|---|---|
| inotify fires on the workspace bind mount | ✅ both in-place writes and atomic-rename saves |
| …for writes made by the **nested toolchain container** | ✅ this is the load-bearing one — see below |
| Full fixed-camera thumbnail render via `bin/openscad` | 0.35 s, of which ~0.20 s is `docker run` startup |
| Node available for the watcher | ✅ v24, `fs.watch` built in, no new install |

The nested-container result matters most: renders are written by a container
started via docker-in-docker, not by a devcontainer process, and if those
writes were invisible to inotify the entire auto-reload story would collapse
regardless of extension quality. They are visible. (The reason the whole
chain is reliable: VS Code Server runs *inside* the container, so editor
saves are in-container writes too — no host→container event propagation
anywhere in the path, which is the part that breaks on Docker Desktop.)

**Debounce is required.** A single atomic-rename editor save produced *two*
inotify events; watchers are noisy generally. A trailing debounce
(~100–200 ms) is the floor, or renders fire against half-written sources.

**Where it runs:** devcontainer side, invoking `bin/openscad` per render, via
`make`. *Rejected:* a long-lived container with the watcher inside it — it
would amortize the 0.2 s startup, but 0.2 s is not a problem worth solving,
and it needs its own lifecycle management plus a second way of reaching the
pinned image, against openscad-image.md's premise that there is exactly one.

## Part 2: what displays it

### The extension route was tried and does not work

Four candidates were read from source and two were tested live in this
devcontainer. **None satisfies remote + hot reload + camera preservation**;
each fails a different one.

| Extension | Updated | Remote/devcontainer | Hot reload | Camera on reload |
|---|---|---|---|---|
| [`misiekhardcore.stl-previewer`](https://github.com/misiekhardcore/stl-previewer) | 2025-10 | ✅ works | ✅ plain overwrite only | ❌ **resets** |
| [`tatsy.vscode-3d-preview`](https://github.com/tatsy/vscode-3d-preview) | 2025-01 | — | ❌ posts a message nothing listens for | — |
| [`slevesque.vscode-3dviewer`](https://github.com/stef-levesque/vscode-3dviewer) | 2020-09 | ❌ green screen ([#32](https://github.com/stef-levesque/vscode-3dviewer/issues/32), unresolved) | ✅ | likely ✅ |
| `planetsensorllc.stl-viewer` | 2026-04 | likely ✅ | ❌ none at all | — |

Measured results for `stl-previewer`, the only one that got as far as a live
test:

| write strategy | result |
|---|---|
| plain overwrite | reloads, but **camera resets** |
| render to temp + atomic `mv` | **no reload** |
| render to temp + `mv` + `touch` | **no reload** |

Two predictions from source-reading did not survive contact with the UI, and
both are worth recording as a caution about this kind of research:

- `stl-previewer` has an explicit `RenderState.cameraPosition` persisted via
  a state manager and re-applied in `createCamera()`. It still resets the
  camera in practice. Reading state-management code does not establish that
  state actually round-trips through a full webview HTML replacement.
- `touch` after an atomic rename was expected to be a cheap rescue for the
  missing change event. It is not, and no confirmed mechanism explains why a
  `touch` produces no event on a path whose plain overwrites do. Recorded as
  an observation, not a diagnosis.

Also note `tatsy.vscode-3d-preview` is a rewrite of the 2020
`vscode-3dviewer` that kept the extension-side
`webview.postMessage("modelRefresh")` while its new `media/viewer.js` never
calls `acquireVsCodeApi()` and registers no `message` listener. Its
`hotReload` setting, default on, does nothing. **An extension having a
`hotReload` option is not evidence that hot reload works.**

### What this does and does not indict

It does **not** indict the build toolchain. Everything verified about that
held: the pinned image, the `bin/` shim, docker-in-docker mount semantics,
inotify seeing nested-container writes, and 0.35 s renders. The failure is
narrowly in the third-party VS Code 3D-viewer ecosystem, which is thinner
and worse maintained than its extension count suggests.

For the record, the structural argument for webviews was sound and is not
what failed: unlike `Antyos.openscad` — which spawned a **native Qt process
inside the container** needing an X display there — a webview renders in the
local VS Code UI process on the local GPU. That distinction held up.
`vscode-3dviewer`'s green screen is a resource-URI bug in a stale extension,
not the same class of problem.

### Direction: serve the model ourselves

Every failure above is downstream of one decision: **depending on someone
else's file watcher to trigger someone else's reload.** Serving the model
from a small local server removes that dependency and, with it, the entire
class of problem:

- **The reload signal is pushed, not watched.** The watcher sends it after
  the `mv` completes. Nothing observes the file, so the atomic-rename
  question is moot and the truncated-read window closes completely — the
  viewer is never told about a file that is not finished.
- **Camera is preserved by construction**, because only the geometry is
  replaced in a live three.js scene; the scene and its `OrbitControls` are
  never torn down.
- **Debounce is ours**, so a streamed render cannot cause flicker.
- **3MF can be served directly** via three.js's `3MFLoader`, removing the
  constraint below that the preview loop must derive STL for a viewer's
  sake. initial-design.md already makes 3MF the primary format.
- **It works in a real browser** — bigger window, better acceleration — as
  well as in VS Code's Simple Browser tab, via devcontainer port forwarding,
  which is first-class and needs no extension at all.
- **No third-party dependency that can regress**, which three of the four
  extensions above demonstrably did.

The cost is code we own: a static page with three.js + `OrbitControls`, an
SSE endpoint for the reload signal, and a file handler. Node is already in
the devcontainer. This is the most work of any option considered, and the
evidence now justifies it — the cheaper options were tried first and failed
on their merits, which is the right order to have learned it in.

Run the server on the devcontainer side, **not** inside the toolchain image:
the toolchain image is deliberately a stateless one-shot command runner, and
a server inside it would need its port published to the devcontainer and
then forwarded again.

### Stopgap, no longer needed

Before the server existed, `stl-previewer` plus plain overwrite was the only
working option, at the cost of re-rotating after every save. The prototype
supersedes it; recorded only so the option is not rediscovered as if new.

## Design requirements this imposes on the build

1. **Renders should still land atomically.** OpenSCAD streams its output: a
   single STL render produced ~19 incremental writes, with the target file
   visible and growing throughout. Serving our own model makes this less
   urgent than it was — nothing watches the file, and the "done" signal is
   only sent after the render returns — but rendering to a temp path and
   `mv`-ing into place is still correct, because it keeps a concurrent HTTP
   GET (a browser refresh mid-render) from reading a partial mesh.

   Worth stating plainly: this is a constraint **previews impose on the build
   layer that CI does not care about**, so it doesn't get optimized away
   later by someone reading only initial-design.md.

2. **The temp filename must keep a format-valid suffix.** OpenSCAD infers
   export format from the extension and hard-errors on an unknown one
   (`-o foo.stl.tmp` → *"Invalid suffix tmp"*). Use `.tmp-foo.stl` (dot-
   prefixed, suffix intact) or pass `--export-format` explicitly.

3. **Debounce the source watcher**, per Part 1.

4. **No STL-for-the-viewer's-sake requirement.** An earlier draft concluded
   the preview loop had to emit STL specifically, because every candidate
   extension was STL-only. Serving our own viewer removes that: three.js has
   a `3MFLoader`, so previews can use the 3MF that initial-design.md already
   makes primary.

## How much confidence this deserves

**Proven by test:**

- inotify sees writes made by the **nested toolchain container** — the
  assumption the whole loop rests on, and the one most likely to have been
  silently false.
- Render speed is a non-issue: ~0.22 s end-to-end, ~0.20 s of it container
  startup.
- The truncated-write hazard is real and reproducible (~19 incremental
  writes per render), and atomic rename fixes it.
- The extension route fails, specifically and for three different reasons —
  see the tables above. This is the finding that changed the design.

**Proven by the prototype** (`viewer/`), the items this section previously
listed as assumed:

- **Camera survives re-render**, in a real browser, for both STL and 3MF.
  This is the property the whole direction was chosen for, and it was the
  one thing that could have invalidated it.
- **`3MFLoader` parses OpenSCAD's 3MF** without special handling.
- Devcontainer port forwarding to the browser is as frictionless as
  expected.
- Debounce behaves: two rapid source edits produce exactly two render
  cycles, not one per inotify event.

**Emergent, and worth keeping:** because a failed render never reaches the
served path, the atomic rename means a syntax error leaves the *last good
model* on screen while the error is reported separately. The preview
degrades to stale rather than to blank, which is the better failure.

Nothing material about the preview design is now unverified. What remains
is integration work, not risk.

## Open questions

- Where iteration output lives. The prototype uses a gitignored
  `viewer/.cache/`, which is right for a standalone tool; once `out/` exists
  the loop should probably render there instead so the preview and a manual
  `make` share one tree rather than rendering twice.
- Whether the watcher runs `make` for the whole tree or a scoped target.
  Full delegation is correct; a `lib/` edit rebuilding twelve parts
  mid-iteration may still be slower than wanted.
- Whether the server serves one part at a time (as the prototype does, via a
  CLI argument) or an index of everything built. The latter is more useful
  and not much harder, but invites scope creep toward "a whole local
  gallery," which is not the goal.
- Whether this ever merges with the deferred thumbnails. They share the
  watch loop and the render path; only the output format and the
  committed/disposable question differ.

## Possible future improvements

Not blocking, and not currently planned — recorded so they are not
rediscovered from scratch.

- **Serve three.js locally.** The viewer pins `0.185.1` via importmap from
  unpkg, so there is no preview without network access to the CDN. Fetching
  it once into the gitignored cache and serving it from there would make the
  viewer work offline after first run without checking a third-party asset
  into the repo. Deliberately deferred: it costs a little complexity for a
  case (working offline) that has not actually come up.

## Current state

The caveat this section used to carry is spent: `parts/`, `lib/`, `tools/` and
the `Makefile` all exist, so the conversion it anticipated has happened.
`viewer/server.mjs` watches `parts/` and `lib/` and calls `make` — it no longer
renders a nominated file directly through `bin/openscad`, and it no longer
looks at the old flat `scad/` tree, which is gone.

`make` deciding what to rebuild is what makes a `lib/` edit that moves several
parts at once behave correctly, which the interim "render the nominated file"
prototype could not have done.
