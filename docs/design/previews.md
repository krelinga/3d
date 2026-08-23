# Previewing rendered output from the devcontainer

Status: draft — direction chosen, one blocking question left to answer in the UI
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

**Deferred, deliberately:** the committed fixed-camera PNGs that
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
    ┌─────────────┐   watches the tree, debounces, decides nothing
    │   watcher   │
    └──────┬──────┘
           │ runs
           ▼
    ┌─────────────┐   decides what actually needs rebuilding
    │    make     │   (already has the dependency graph)
    └──────┬──────┘
           │ bin/openscad, render to temp + atomic rename
           ▼
      out/…/foo.stl
           │
           ▼
    ┌─────────────┐   watches that one file, reloads, keeps your camera
    │  webview 3D │
    │  viewer ext │
    └─────────────┘
```

Two independent watchers, which is not a redundancy: ours watches *sources*
to trigger builds, the extension's watches *one output* to trigger a redraw.
Neither knows about the other.

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
| Full fixed-camera PNG render via `bin/openscad` | 0.35 s, of which ~0.20 s is `docker run` startup |
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

### Why a webview extension can work where `Antyos.openscad` could not

Worth being precise, because the surface similarity is misleading.
`Antyos.openscad` spawned a **native Qt process inside the container**, which
needed an X display there — hence `qt.qpa.xcb: could not connect to display`.
A webview extension is structurally different: the extension host runs in the
container, but the webview renders in the **local** VS Code UI process on the
local GPU, with VS Code proxying the file out. Nothing needs a display inside
the container. The previous failure does not recur.

### Extension survey — read from source, and the obvious pick is wrong

All three candidates were cloned and read, because "has a file watcher" turns
out not to mean "hot reload works."

| Extension | Last commit | Reload path | Verdict |
|---|---|---|---|
| [`stl-previewer`](https://github.com/misiekhardcore/stl-previewer) | 2025-10 | watcher → `render()` → replaces `webview.html` | ✅ **recommended** |
| [`vscode-3d-preview`](https://github.com/tatsy/vscode-3d-preview) | 2025-01 | watcher → `postMessage('modelRefresh')` → **nothing listens** | ❌ dead feature |
| [`vscode-3dviewer`](https://github.com/stef-levesque/vscode-3dviewer) | 2021-02 | watcher → `postMessage` → listener present and handles it | ⚠️ works, unmaintained |

The trap: **`vscode-3d-preview` looks like the best choice and isn't.** It
has an explicit `hotReload` setting (default on) and is recent. But it is a
rewrite of the 2021 `vscode-3dviewer`, and while it kept the extension-side
`webview.postMessage("modelRefresh")`, its rewritten `media/viewer.js` never
calls `acquireVsCodeApi()` and registers no `message` listener anywhere. The
message goes nowhere. The 2021 original it descends from *does* have the
listener (`media/viewer.js:39` registers it, `:93` handles `modelRefresh`) —
so the rewrite silently regressed the feature.

**`stl-previewer` is the pick**: newest, actively maintained, and its reload
path is complete. It reloads by replacing the webview HTML wholesale, which
would normally reset your camera on every save — the exact failure that would
make this workflow infuriating — except it persists camera position
explicitly (`RenderState.cameraPosition`, re-applied in `createCamera()`). So
the angle you rotated to should survive a re-render, which is precisely the
property this whole approach exists to provide.

### Consequence: the preview loop must emit STL

All three viewers are STL-only; **none reads 3MF.** initial-design.md makes
3MF primary and STL derived, so this costs nothing — the STL already exists —
but it does mean the preview target is specifically the `.stl`, and a future
"3MF only" optimization would break previewing.

## Design requirements this imposes on the build

These fall out of the testing and are not optional.

1. **Renders must land atomically.** OpenSCAD streams its output: a single
   STL render produced ~19 incremental `change` events, with the target file
   visible and growing the whole time. A viewer reloading on the first event
   reads a truncated mesh. The build must render to a temp path and `mv` into
   place — `rename(2)` within a filesystem is atomic, so the final path only
   ever exists complete.

   This is a constraint **previews impose on the build layer that CI does not
   care about**, which is worth stating plainly so it doesn't get optimized
   away later by someone reading only initial-design.md.

2. **The temp filename must keep a format-valid suffix.** OpenSCAD infers
   export format from the extension and hard-errors on an unknown one
   (`-o foo.stl.tmp` → *"Invalid suffix tmp"*). Use `.tmp-foo.stl` (dot-
   prefixed, suffix intact) or pass `--export-format` explicitly.

3. **Debounce the source watcher**, per above.

## How much confidence this deserves

**Proven here, by test:**

- inotify sees nested-container writes — the assumption the whole design
  rests on, and the one most likely to have been silently false.
- Render speed is a non-issue (0.35 s end-to-end).
- The truncated-read hazard is real, reproducible, and fixed by atomic rename.
- `stl-previewer`'s reload path and camera persistence exist in source, in
  the current release.

**Not proven, and honest about it** — these need a human in the UI, and
together they are maybe fifteen minutes of checking:

- **The one blocking question:** whether `stl-previewer`'s watcher fires on
  an *atomic rename*. Its watcher handles `onDidChange`; replacing a file via
  `mv` gives the path a new inode, which VS Code may surface as a create
  rather than a change — and the extension does not listen for create. If it
  misses the event, the fix is cheap (`touch` the file after the `mv`, or
  drop atomicity and accept occasional truncated reads), but it must be
  checked, because atomic rename is required by (1) above and could defeat
  the very reload it's protecting. **This is the thing to test first.**
- Whether camera persistence actually survives visually, as opposed to
  reading correct.
- Whether the webview handles meshes of realistic size smoothly over the
  remote resource proxy.

Nothing found so far suggests the approach is unsound; the risk is
concentrated in that one interaction, and it has a known workaround.

## Open questions

- Where iteration output lives. Rendering into the committed preview path
  would keep the working tree permanently dirty while iterating; a gitignored
  scratch location avoids that. Less fraught than it was when still images
  were the plan, since the interactive STL is not the reviewed artifact
  anyway — but it needs deciding once `out/` exists.
- Whether the watcher runs `make` for the whole tree or a scoped target. Full
  delegation is correct; a `lib/` edit rebuilding twelve parts mid-iteration
  may still be slower than wanted.
- Whether to pin the extension version in `devcontainer.json`. Given that
  `vscode-3d-preview` regressed its reload in a rewrite, an unpinned
  `stl-previewer` could do the same. Weighed against the maintenance cost of
  pinning, and the fact that the last extension added here had to be removed.
- Fallback if `stl-previewer` disappoints: the 2021 `vscode-3dviewer` has a
  verified-complete reload path but is four years stale, and a local web
  server with an own-built viewer (full control over reload and camera, most
  code to own) remains available.

## Current-state caveat

As with the rest of `docs/design/`, this rests partly on unbuilt work:
`parts/`, `lib/`, `tools/`, and the `Makefile` do not exist yet, so "the
watcher runs `make`" has nothing to call today.

An interim version is cheap and worth doing first regardless: watch
`scad/**/*.scad`, render the changed file directly with `bin/openscad` to a
temp path, `mv` into place, open the result in `stl-previewer`. That answers
the blocking question above without waiting on the build system, and it is
the piece of this design most likely to invalidate the rest.
