# OpenSCAD Model Repository — Design

Status: current
Scope: repository structure, versioning, and release automation for OpenSCAD
sources that build 3MF/STL artifacts.

## Premise

Mesh files are build outputs, not source. They are derived, large, and
non-diffable. The repository holds `.scad` source; artifacts are produced by CI
and published as GitHub release assets, the same way a compiled binary is.

This eliminates the common failure mode in model repos where someone edits a
`.scad` file and forgets to re-export the mesh, leaving the two silently out of
sync.

## Overview

A monorepo of OpenSCAD parts that CI compiles into meshes, the way a source repo
compiles into binaries. Each part declares its own version and variants in a
small YAML file beside its source. Every pull request builds every part; merges
to `main` check whether any part's declared version has stopped describing what
it actually builds; releases are cut per part, on demand, and carry the meshes
as assets.

### Vocabulary

The words below are used precisely throughout, and several of them are easy to
conflate.

| Term | Means |
|---|---|
| **Part** | One printable thing. One leaf directory under `parts/`, named by that directory. The unit of versioning and of release. |
| **Category** | Any directory under `parts/` without an `entry.yaml`. Groups parts and holds nothing but directories. Organizational only — invisible to tags, filenames, and releases. |
| **Variant** | One parameterization of a part (`m5_short`). Shares its part's version; ships as its own file. |
| **Catalog** | The set of `entry.yaml` files. Hand-authored, committed. Declares **intent** — what should exist, at what version. |
| **Build record** | `build-record.json`, generated per release, never committed. Records **outcome** — what actually came out, and from which toolchain. |
| **Thumbnail** | A committed PNG of one variant, fixed camera, diffed on GitHub during review. |
| **Preview** | The live, rotatable render used while editing. Never committed; see [previews.md](previews.md). |
| **Metrics** | Bounding box, volume, and area measured from a built mesh. The comparable summary of geometry. |
| **Baseline** | The metrics from a part's most recent release. What current output is compared against. |
| **Drift** | A part whose output has changed but whose declared version has not. |

Catalog and build record are the pair most worth keeping straight: one is what
you meant, the other is what happened.

### Lifecycle

```
   edit parts/bracket/source.scad
             │
             ▼
   ┌──────────────────┐   pr.yml
   │   pull request   │   build every part · assert every mesh · refresh
   └────────┬─────────┘   thumbnails · post a metrics diff as a comment
            │ merge
            ▼
   ┌──────────────────┐   main.yml
   │       main       │   re-measure · file a drift issue for any part whose
   └────────┬─────────┘   output moved but whose version did not
            │ you decide the change is worth shipping
            ▼
   ┌──────────────────┐   release.yml (workflow_dispatch)
   │   bracket/v2.3   │   read version · cut tag · clean build · attach
   └──────────────────┘   meshes + build record · update the README index
```

### The four ideas doing the work

Most of the rest of this document follows from these.

1. **The directory listing is the catalog.** A part is a leaf directory; its
   name, its source file, and its parameter file all have fixed names. Nothing
   is declared twice, so nothing can disagree with itself.
   → [The catalog](#the-catalog-one-entryyaml-per-part)

2. **The toolchain is pinned by image digest, declared in exactly one place.**
   There is no current stable OpenSCAD release, and output shifts between
   snapshots, so "same version" is not a strong enough claim. How the pin is
   declared and how local dev and CI both reach it is
   [its own design doc](openscad-image.md), not repeated here.
   → [Reproducibility](#reproducibility)

3. **Geometry is compared by measurement, never by bytes.** OpenSCAD's output is
   not reproducible even run to run, so every comparison in this design —
   change detection, release notes, thumbnail freshness — is a tolerance check on
   measured quantities rather than a hash.
   → [Reproducibility](#2-output-is-not-deterministic-run-to-run)

4. **Declared versions are kept honest after the fact, not enforced up front.**
   A shared-library edit can move a dozen parts at once; requiring version bumps
   in that PR would be wrong as often as it was right. Instead, drift is
   detected on merge and filed as an issue, and re-tagging stays a deliberate
   decision.
   → [What drift detection is for](#what-drift-detection-is-for)

## Hosting decision

GitHub Packages supports a fixed set of ecosystems (Container registry, Docker,
RubyGems, npm, Maven/Gradle, NuGet). There is no generic artifact type, so it is
not an option here.

| Channel | Use | Notes |
|---|---|---|
| **Release assets** | Primary distribution | Permanent, unauthenticated download URLs on public repos. 2 GB per file. |
| **Actions artifacts** | PR / branch build artifacts | Default 90-day retention. Fine for non-durable output. |
| **ghcr.io via ORAS** | Not used | Technically possible to push arbitrary files as OCI artifacts, but requires consumers to run `oras`. Rejected as user-hostile for this use case. |
| **ghcr.io (container)** | Build image | Used, but for the pinned toolchain image — not for models. |

### What GitHub actually renders

GitHub renders committed `.stl` files under 10 MB with an interactive 3D viewer.
It does **not** offer a before/after diff for them — the revision slider was
removed. Images, by contrast, still get the full 2-up / swipe / onion-skin diff.

The consequence is not cosmetic: **the committed thumbnails are the only
visual diff available.** That makes them load-bearing rather than decorative,
and it settles the thumbnail decision below.

## Repository layout

```
parts/                    # parts may be nested in category directories
  bracket/                # the leaf directory name IS the part name
    source.scad           # top-level, one printable part
    params.json           # OpenSCAD customizer parameter sets → variants
    entry.yaml            # catalog entry
  printer-mods/           # a category — no entry.yaml of its own
    spool-holder/
      source.scad
      entry.yaml          # no params.json — a single-variant part
lib/
  krelinga/               # own shared modules
  BOSL2/                  # submodule, pinned to a release tag
thumbnails/               # committed PNGs for PR review; see Thumbnails
  bracket/
    m5_short.png          # one per variant
    m5_long.png
  spool-holder/
    spool-holder.png      # single-variant part; categories are not mirrored here
tools/
  catalog.py              # load + validate every entry.yaml
  gen_rules.py            # entry.yaml → generated make rules
  metrics.py              # mesh metrics + manifold assertion
  drift.py                # compare metrics against a baseline release
  render_index.py         # regenerate the README index table
bin/                      # reaches the pinned toolchain image; see openscad-image.md
viewer/                   # live iteration preview server; see previews.md
Makefile
.devcontainer/
  devcontainer.json
  Dockerfile              # the toolchain image is built from this repo
.github/workflows/{pr.yml,main.yml,release.yml,image.yml}
README.md                 # contains a generated index block
```

One directory per part, always at HEAD. Historical versions are recovered from
git tags, not from parallel directories.

### Rejected alternative: version-encoded paths

`/<part>/<major>/<minor>.scad` was considered and rejected. It keeps every
historical version in the working tree, which means:

- Bumping a version is a file copy, permanently forking each model from its own
  past. A fix to shared logic must be applied to N copies or knowingly skipped.
- `git log parts/bracket/` shows "new file added" rather than a diff, defeating
  the intent of relying on git history for fine-grained change tracking.
- The tree grows without bound with source that is never built.

## The catalog: one `entry.yaml` per part

**The directory listing is the catalog.** CI globs `parts/**/entry.yaml`; a leaf
directory with no `entry.yaml` is a hard error, not a silent omission.

*Rejected alternative:* a single hand-authored `models.yaml` at the repo root.
It duplicates the directory structure — a part's name lives both in its path and
in the YAML — and nothing stops a part directory from being absent from it, in
which case it silently never builds. Per-part files make that orphan case
structurally impossible.

### Categories: nesting is allowed, and is purely organizational

The glob is recursive, so parts may be grouped to any depth:

```
parts/
  brackets/
    2020-corner/entry.yaml       # part name: 2020-corner
    2020-tee/entry.yaml          # part name: 2020-tee
  printer-mods/
    spool-holder/entry.yaml      # part name: spool-holder
  mount/entry.yaml               # part name: mount — nesting is optional
```

**The part name is the leaf directory name, never the path.** `2020-corner`
releases as tag `2020-corner/v2.3`, builds to `2020-corner-v2.3-m5_short.3mf`,
thumbnails to `thumbnails/2020-corner/m5_short.png`. Nothing downstream of the
catalog knows or cares which category a part sits in.

Two things follow. **Categories are free to reorganize** — re-shelving a part is
a directory move that changes no tag, no filename, and no release, so the cost
of getting the taxonomy wrong is close to zero. And **nesting has no depth
limit**, because depth never reaches a name: `parts/a/b/c/d/` is as workable as
`parts/d/`.

Two rules keep it unambiguous:

- **A directory is a category or a part, never both.** A directory containing
  `entry.yaml` must not contain any descendant `entry.yaml`.
- **Part names are globally unique across `parts/`.** They are tag prefixes and
  filename components, so `brackets/spacer` and `printer-mods/spacer` would
  collide in the tag namespace even though the paths differ.

One consequence for tooling: a part's path can no longer be constructed from its
name. `catalog.py` resolves name → path, and `release.yml` asks it rather than
building `parts/<name>/entry.yaml` itself.

Categories are structure and nothing else — they hold directories, not files.
Grouping parts by what they assemble into is a related but separate problem, and
one this design does not take on; see [Out of scope](#out-of-scope).

#### Rejected alternative: the full path as the part name

Naming a part `brackets/2020-corner` would drop the global uniqueness rule,
which is a real cost of the chosen design — it means adding a part requires
knowing what exists elsewhere in the repo, which is precisely the kind of
non-local constraint a directory hierarchy is supposed to remove. Git handles
the resulting tags fine (`refs/tags/brackets/2020-corner/v2.3` is legal, and the
category-or-part rule already prevents the ref D/F conflict), and the Actions
tag filter only needs `**/v*` instead of `*/v*`.

It was rejected on artifact filenames. A filename cannot contain `/`, so the
path has to flatten — and `brackets/2020-corner` and `brackets-2020/corner`
flatten to the same string. The filename would stop being a faithful encoding of
the part's identity, in the one artifact that leaves the repository and has to
stand on its own. Flattening also drags the category into every filename, which
would make re-shelving a breaking change and forfeit the freedom described
above.

The trade is really *is a part's category part of its identity?* Path naming
says yes, in the manner of Go module paths and Bazel labels, and accepts moves
as breaking changes. This design says no, and pays for it with one uniqueness
rule that `catalog.py` enforces in a single line.

### Fixed filenames, not declared ones

Exactly one part lives in a leaf directory, so nothing needs to be named twice.
Every part directory has the same three names:

| File | Role | Required |
|---|---|---|
| `source.scad` | the top-level model | yes |
| `params.json` | customizer parameter sets | only for multi-variant parts |
| `entry.yaml` | the catalog entry | yes |

Convention beats declaration here for the same reason per-part files beat one
big `models.yaml`: a name that appears in only one place cannot disagree with
itself. It also keeps `name`, `source`, and `params` out of the schema entirely,
along with the validation rules that would exist to police them.

The one real cost is editor tabs — every open tab reads `source.scad`. VS Code
and OpenSCAD's recent-files list both disambiguate by parent directory, so in
practice you see `bracket/source.scad`, which is the name you wanted anyway.

```yaml
# parts/bracket/entry.yaml
version: "2.3"                # quoted — see below
status: active                # active | deprecated
description: L-bracket for 2020 extrusion
variants:
  - name: m5_short
    param_set: m5_short       # → openscad -P m5_short
  - name: m5_long
    param_set: m5_long
camera: [0, 0, 0, 55, 0, 25, 140]   # fixed thumbnail camera, see Thumbnails
print:
  layer_height: 0.2
  infill: 40
  supports: false
  orientation: flat-on-bed
hardware:
  - M5x20 SHCS
  - M5 t-nut
```

The part name is the directory name. It appears nowhere in the file.

**Quote the version.** Unquoted, YAML parses `2.3` as a float, and version
`2.10` silently becomes `2.1` — which then fails to match tag `bracket/v2.10`
for reasons that take an unpleasant hour to find. `tools/catalog.py` rejects a
non-string `version`.

### Single-variant parts omit `params.json`

A part with no parameter sets has no `params.json` and no `variants:` key. It
builds one artifact from `source.scad` with no `-p`/`-P` flags, and the variant
suffix drops out of the filename: `spool-holder-v1.4.3mf`, not
`spool-holder-v1.4-default.3mf`. Adding a `params.json` later is a rename of the
outputs, which is a version bump anyway.

Declaring `variants:` without a `params.json` is an error, and so is the
reverse.

### Variants are the blessed builds, not the only ones

The variants enumerated in `entry.yaml` are what CI builds, measures, and
releases. They are a curated set, not an exhaustive one — the point of listing
them is that each is a build someone has decided is worth standing behind.

Anyone wanting a size that is not listed builds it themselves. `params.json` is
an ordinary OpenSCAD customizer file, so `source.scad` opens in the GUI with the
parameter sets already populated and editable, and the CLI path is the same one
CI uses:

```sh
openscad --backend=manifold \
         -D bolt_diameter=6 -D leg_length=55 \
         -o my-bracket.3mf parts/bracket/source.scad
```

The README carries a short hand-written **Build your own variant** section
covering this, sitting above the generated index block. That section is the
whole answer — no mechanism in the repo needs to change to support it, which is
the reason this stays curated rather than becoming a parameter-space matrix.

Promoting an ad-hoc size to a blessed variant means adding a `param_set` to
`params.json` and a `variants:` entry. That adds a file to the release without
altering any existing one, so it is a minor bump.

### What validation runs on the catalog

`tools/catalog.py`, called from every workflow and from `make check`:

- a directory with an `entry.yaml` also has a `source.scad`, and has no
  descendant `entry.yaml` (a directory is a category or a part, never both)
- every other directory under `parts/` holds only directories, and contains at
  least one part somewhere beneath it — this catches a typo'd or abandoned
  directory rather than letting it sit there silently
- part directory names are unique across the whole of `parts/`
- every directory name under `parts/`, category or part, matches `^[a-z0-9-]+$`
  (a part's is a tag prefix and a filename component)
- `version` is a string matching `^\d+(\.\d+){0,2}$`, and is normalized to
  three components before use (see below)
- `variants:` and `params.json` are present together or absent together
- every `param_set` named actually exists in `params.json`
- variant names are unique per part and match `^[a-z0-9_]+$` (they end up in
  filenames)
- `camera` is 7 numbers
- no unrecognized top-level keys (catches `paarams:` and friends)

### The print metadata is consumed, not decorative

The release workflow renders `print:` and `hardware:` into a
`bracket-v2.3-PRINT.md` attached to the release, so a downloaded artifact is
self-describing. Metadata that nothing reads rots — if a field is never worth
rendering, it should be deleted from the schema instead.

## `build-record.json` — the build record

Generated by the workflow, attached as a release asset, **never committed**.
Records what actually came out.

```json
{
  "release": "bracket/v2.3",
  "part": "bracket",
  "version": "2.3",
  "commit": "a1b2c3d...",
  "built_at": "2026-08-22T14:03:00Z",
  "image": "ghcr.io/krelinga/3d/openscad-build@sha256:9f2c...",
  "openscad_version": "OpenSCAD 2026.01.12 (git 4a8c1f2)",
  "artifacts": [
    {
      "variant": "m5_short",
      "files": ["bracket-v2.3-m5_short.3mf", "bracket-v2.3-m5_short.stl"],
      "bytes_3mf": 71204,
      "bytes_stl": 184320,
      "bbox": [40.0, 40.0, 20.0],
      "volume_mm3": 8421.6,
      "area_mm2": 5310.2,
      "facets": 3684,
      "watertight": true
    }
  ]
}
```

**`image` is the digest, and it is the field that matters.** A version string
like `"2026.01"` does not identify anything reproducible; the digest does. The
human-readable `openscad_version` stays for eyeballing, but tooling keys on the
digest.

**Why the SHA matters:** a part's identity is really (part version, build
commit, toolchain digest). If `lib/` changes without any part version changing,
two different files can both honestly be labelled `bracket v2.3`. The build
record makes them distinguishable after the fact.

**`facets` is recorded but is not a drift signal.** See Reproducibility.

## Versioning

### Part versions — interface compatibility

Declared in `entry.yaml`. Semantics are anchored to physical fit, which makes the
boundaries far less arbitrary than in software:

- **Major** — will not drop into the same assembly. Mounting pattern moved,
  different mating hardware, envelope changed.
- **Minor** — geometry changed, interface holds. Thicker wall, added fillet,
  better print orientation. An already-printed old copy still fits.
- **Patch** — no functional geometry change. Label text, tolerance nudge within
  spec, source refactor.

**Declared versions are normalized to three components.** `entry.yaml` may say
`1`, `1.0` or `1.0.0`; all three mean the same thing and all three produce
`v1.0.0` in the tag, in every artifact filename, in the build record and in the
README index.

Padding happens once, in `catalog.py`, rather than at each use site. The reason
is that a version is identity-bearing — it is part of the tag and of every
filename that leaves the repository — so two spellings of the same version must
not be able to name two different releases of the same thing. Writing the short
form stays perfectly fine; it simply is not a second form downstream.

### Tags — one release per part

Slash-namespaced, directory-scoped tags: `bracket/v2.3`, matched as
`refs/tags/*/v*`. This is the same pattern Go modules and most Bazel monorepos
use.

`bracket-v2.3` would work equally well as git, but the tag glob, the tag parser,
and the release-notes generator all hard-code one form or the other, so the
choice has to be made once rather than left open.

**Version boundary = compatibility boundary.** Parts that must change in
lockstep (a bracket and the mount it mates with, if only meaningful together)
share one directory and one version rather than being versioned separately.

### The tag is created by CI, not by hand

`release.yml` is a `workflow_dispatch` taking a part name. It reads `version`
from that part's `entry.yaml` on the selected ref, refuses if a tag for that
version already exists, creates the tag itself, and releases.

The tag therefore cannot disagree with the catalog, and you cannot tag a commit
whose catalog says something else.

*Rejected alternative:* push the tag by hand and have CI reject it when the
version disagrees with the catalog. That is a check for an error class that does
not need to exist. A cheap version of the check survives inside `release.yml`
anyway, for the case where a tag arrives by some other route.

### Deprecating a part

`status: deprecated` in `entry.yaml`. Deprecated parts are still built and still
drift-checked (so they do not quietly break), but they are excluded from the
README index's main table and listed in a "Deprecated" section beneath it, with
their last release linked. Deleting the directory is also allowed; the tags and
releases persist regardless, which is the point of releases.

## Build

### Render once, derive the rest

OpenSCAD emits **3MF only**. The STL is derived from the 3MF with `trimesh`, and
the metrics are computed once on that same loaded mesh. All three outputs
provably describe one mesh, and render time is halved.

This matters because OpenSCAD's output is not deterministic run to run (below):
one invocation per output format would let the `.3mf` and the `.stl` in a single
release be two different triangulations of the same model.

```sh
# One render per variant. 3MF is the source of truth for that build.
openscad --backend=manifold --hardwarnings \
         -p parts/bracket/params.json -P m5_short \
         -d build/deps/bracket-m5_short.d \
         -o out/bracket/bracket-v2.3-m5_short.3mf \
         parts/bracket/source.scad

# STL + metrics from that same 3MF, one load, one pass.
python3 tools/metrics.py out/bracket/bracket-v2.3-m5_short.3mf
# → bracket-v2.3-m5_short.stl, bracket-v2.3-m5_short.metrics.json
```

`--backend=manifold` is dramatically faster than CGAL on boolean-heavy models,
which matters when every CI run rebuilds everything. It became non-experimental
in 2024.09.28 but is **still not the default** — it must be passed explicitly.

**`--hardwarnings` is worth passing, but it is not the guard against bad
geometry.** It promotes warnings to failures, which is right, and
`--check-parameter-ranges=true` likewise. But measured behaviour on the pinned
toolchain is narrower than it sounds:

| result | exit code | file written | what stops the build |
|---|---|---|---|
| empty top-level object | 1 | no | OpenSCAD itself |
| non-manifold solid | 0 | yes | `tools/metrics.py` only |

Two cubes meeting at a single edge build to `Genus: -1` and exit 0 **with or
without** `--hardwarnings`. So the per-mesh assertions are not a second
opinion on top of OpenSCAD — for non-manifold output they are the only
opinion, which is why they fail the build rather than warn.

### The dependency file does not cover everything

`openscad -d` records `use`/`include`/`import`/`surface` dependencies. It does
**not** record:

- `params.json` (edit a parameter set → no rebuild)
- `entry.yaml` (bump the version → the output filename changes but make may not
  notice)
- the toolchain image

The first two are added as explicit prerequisites in the generated make rules.
The third is handled by keying the whole `out/` tree on the image digest — CI
starts from a clean tree anyway, and locally a digest change should be treated
as `make clean`.

### Makefile

Rules are generated from the catalog rather than written by hand, because the
variant list lives in YAML:

```makefile
OPENSCAD ?= openscad
OUT      := out
BUILD    := build
# $(wildcard) has no ** — find is the only way to reach nested parts.
PARTS    := $(shell find parts -name entry.yaml)

.PHONY: all pr check index thumbnails clean
.DEFAULT_GOAL := all

$(BUILD)/parts.mk: $(PARTS) tools/gen_rules.py
	@mkdir -p $(BUILD)
	python3 tools/gen_rules.py > $@

-include $(BUILD)/parts.mk        # defines ARTIFACTS and THUMBNAILS

# Both targets come after the include, so the variables are already defined.
all: $(ARTIFACTS)
thumbnails: $(THUMBNAILS)

# Everything CI can verify without building. The index check belongs here:
# without it `make check` passes on a stale index and the first sign of
# trouble is a failed PR.
check:
	python3 tools/catalog.py --validate
	python3 tools/render_index.py --check

# The generated-artifact counterpart to `make thumbnails` -- both produce
# something committed that CI then verifies you did not forget.
index:
	python3 tools/render_index.py

# The one target anyone needs to remember: does what CI does, in CI's order,
# regenerating the committed artifacts rather than only reporting them stale.
# Forces the thumbnails, so it cannot disagree with CI about freshness.
pr:
	$(MAKE) catalog-check && $(MAKE) -j all && $(MAKE) -B thumbnails && $(MAKE) index

clean:
	rm -rf $(OUT) $(BUILD)
```

The generated `parts.mk` is auto-remade by make before the include is resolved,
so editing an `entry.yaml` regenerates the rules on the next `make` with no extra
step.

`tools/gen_rules.py` emits, per variant:

```makefile
# Grouped target (&:, GNU make ≥ 4.3): one recipe, three outputs. Without the
# grouping, deleting just the .stl would not trigger a rebuild.
$(OUT)/bracket/bracket-v2.3-m5_short.3mf \
$(OUT)/bracket/bracket-v2.3-m5_short.stl \
$(OUT)/bracket/bracket-v2.3-m5_short.metrics.json &: \
		parts/bracket/source.scad \
		parts/bracket/params.json \
		parts/bracket/entry.yaml
	@mkdir -p $(@D) $(BUILD)/deps
	$(OPENSCAD) --backend=manifold --hardwarnings \
	  --check-parameter-ranges=true \
	  -p parts/bracket/params.json -P m5_short \
	  -d $(BUILD)/deps/bracket-m5_short.d \
	  -o $(OUT)/bracket/bracket-v2.3-m5_short.3mf \
	  parts/bracket/source.scad
	python3 tools/metrics.py $(OUT)/bracket/bracket-v2.3-m5_short.3mf

-include $(BUILD)/deps/bracket-m5_short.d
```

`metrics.py` loads the 3MF once and writes both the `.stl` and the
`.metrics.json` from that single in-memory mesh.

For a single-variant part the same rule is emitted without `-p`/`-P` and without
the `params.json` prerequisite, targeting
`$(OUT)/spool-holder/spool-holder-v1.4.3mf`.

Note that the version number is baked into the output filename, so a version
bump changes the target name and the old artifact lingers in `out/`. CI always
starts clean; locally, `make clean` after a bump.

Run with `make -j$(nproc)`. Parts are independent, and OpenSCAD is
single-threaded per invocation.

## Reproducibility

Three separate instabilities, each needing a different answer.

### 1. There is no current stable OpenSCAD

The latest stable release is **2021.01**, now five years old. It has no
`--backend` flag, no manifold backend, an old lib3mf, and needs `xvfb-run` for
PNG export. Every feature this design relies on exists only in dev snapshots.

Therefore the pin is a **dev snapshot image digest**, not a version number:

```
ghcr.io/krelinga/3d/openscad-build@sha256:9f2c...
```

built by `image.yml` `FROM openscad/openscad:dev.2026-01-12`, plus `python3`,
`trimesh`, `pyyaml`, `imagemagick`. Exactly where the digest is declared, and
how local dev and CI both reach it, is [openscad-image.md](openscad-image.md)
— not repeated here to avoid the two docs drifting apart.

#### The image is built from this repository

`.devcontainer/Dockerfile` and `.github/workflows/image.yml` live here, not in a
separate repository. The image has exactly one consumer, and keeping the
Dockerfile beside the digest that references it means a toolchain change and its
consequences are visible in one place. It graduates to its own repository under
the same rule as `lib/`: when a second repository needs it, and not before.

Two wrinkles follow from it being in-repo, both minor but both surprising
the first time:

- **`image.yml` needs `permissions: packages: write`.** It's the one workflow
  that pushes to the registry rather than pulling from it — every other
  workflow reaches the pinned image read-only, and (see
  [openscad-image.md](openscad-image.md)) none of them run inside it via
  `container:`, `image.yml` included.
- **A pin bump is necessarily two commits.** The new digest does not exist until
  the image is built and pushed, so the Dockerfile edit and the digest update
  cannot be the same PR. Flow: merge the Dockerfile change → `image.yml` builds
  and pushes → the digest is now known → update the reference. Between the two,
  `main` still builds on the old image, which is correct, not broken. Where
  that reference lives, and how many places need updating, is
  [openscad-image.md](openscad-image.md)'s concern.

Bumping the pin is a deliberate PR. Expect it to change output — see the
rebaseline case below.

### 2. Output is not deterministic run to run

OpenSCAD issue [#4931](https://github.com/openscad/openscad/issues/4931) (open):
the same binary on the same input produces different meshes across runs —
different normals, not merely reordered triangles.

The consequences run deeper than "do not compare checksums":

- **Facet count can change between two runs of the same image.** It is recorded
  in the build record for information, but it must **not** trigger drift.
- Metric comparison is **tolerance-based**, never equality:
  - bbox: absolute, 1e-3 mm
  - volume: relative, 1e-4
  - area: relative, 1e-4
- A "canonical geometry hash" over rounded, sorted vertices is also rejected —
  it fails for the same reason, since the tessellation itself varies.

### 3. 3MF output varies with the lib3mf version

Issue [#5800](https://github.com/openscad/openscad/issues/5800): lib3mf 2.4
writes namespace attributes that 2.3.1 did not. 3MF is therefore excluded from
any byte-level comparison, and lib3mf is pinned transitively by the image
digest.

### Also pin `$fa` / `$fs` / `$fn` explicitly

The special-variable defaults are global state in the binary. Set them in a
shared `lib/krelinga/defaults.scad` included by every part rather than inheriting
whatever the snapshot ships, so a toolchain bump does not silently retessellate
every curve.

## Thumbnails

**Two visual representations exist in this repo, and they are named apart on
purpose.** They answer different questions and have nearly opposite
requirements:

| | **Thumbnails** — this section | **Previews** — [previews.md](previews.md) |
|---|---|---|
| Question | "should this change ship?" | "did my edit do what I meant?" |
| Audience | a PR reviewer, later | the author, right now |
| Form | committed fixed-camera PNG | live, rotatable 3D in a browser |
| Lifetime | versioned in git, diffed on GitHub | disposable, never committed |
| Camera | deliberately fixed, so a diff shows only what moved | freely orbited, and preserved across re-renders |

**"Thumbnail" always means the committed PNG; "preview" always means the live
interactive one.** The rest of this section specifies thumbnails. Previews have
[their own design doc](previews.md), and exist for two reasons this design
creates but does not solve: the devcontainer is headless, so no OpenSCAD GUI
can reach the screen, and a fixed-camera still image cannot answer "is the
back of this part right." Broadly, it works by watching sources, re-rendering
through the same pinned toolchain, and pushing the result to a small local
server whose viewer swaps geometry without disturbing the camera.

The two are expected to share the watch loop and the render path eventually —
only the output format and the committed/disposable question differ — but
that merge is deferred rather than assumed.

One committed PNG per variant, rendered by `make thumbnails` (or `make pr`,
which regenerates it along with everything else CI checks), committed by you,
with CI verifying freshness.

Rationale: with no STL revision diff on GitHub, the PNG diff is the only visual
review available, and it needs to be in the PR — which rules out a bot that
commits regenerated images after merge. Size is not a concern: an 800×600 render
is roughly 60 KB, so 20 parts × 3 variants is about 4 MB.

Path is `thumbnails/<part>/<variant>.png`; a single-variant part renders to
`thumbnails/<part>/<part>.png`, mirroring how the variant suffix drops out of the
artifact filenames.

### Fixed camera per part

`--camera` and `--imgsize` come from `entry.yaml`. Do **not** use
`--viewall --autocenter`: it reframes when the model's size changes, so a
2 mm wall change produces a whole-image diff and the actual change becomes
invisible. A fixed camera means the diff shows only what moved.

```sh
openscad --backend=manifold --render \
         --imgsize=800,600 --camera=0,0,0,55,0,25,140 \
         --colorscheme=Tomorrow \
         -p parts/bracket/params.json -P m5_short \
         -o thumbnails/bracket/m5_short.png parts/bracket/source.scad
```

Headless rendering works without X on dev snapshots (built-in EGL). On a release
image it would need `xvfb-run -a` and `docker --init` — another reason the pin
is a dev snapshot.

### The freshness check compares rendered pixels

CI regenerates the thumbnails and fails if any differs from what is committed
by more than a measured number of pixels. Byte equality is the fast path and
the ordinary case; the image comparison runs only on files that moved:

```sh
make -B thumbnails
git diff --quiet -- thumbnails/ && pass          # ordinary case, no image work
# else, for each changed file:
magick compare -metric AE <committed> <regenerated> null:   # fail past 50 px
```

This replaced an exact byte comparison. The reasoning for that original choice
is preserved below, because it is still what keeps the tolerance small — what
changed is one measured fact, not the argument.

CI must **force** the regeneration (`make -B thumbnails`). A fresh checkout
gives every file the same mtime, so an ordinary `make thumbnails` concludes the
committed PNGs are already current, rebuilds nothing, and the comparison then
passes trivially — a check that silently tests nothing. That bug shipped once,
and only surfaced because a test was written to make the gate fail: locally the
source really is newer than the PNG, so make rebuilds and the check appears to
work.

#### Why not a pixel tolerance

An earlier version of this design specified an ImageMagick comparison failing
past 0.5% of pixels, reasoning that unstable tessellation would otherwise make
byte comparison permanently red. Measurement says otherwise, and splits the
question in two:

- **Meshes are non-deterministic, as feared.** Two clean builds of the same
  sources produce `.3mf` files with different checksums, consistent with
  upstream [#4931](https://github.com/openscad/openscad/issues/4931).
- **Rendered PNGs are not.** Fifteen consecutive regenerations across all
  parts produced byte-identical images every time. Rasterizing at 800×600
  does not surface vertex-level variation.

So the tolerance was guarding a path the instability does not reach, and it
was not free: it silently accepted real changes. A 0.62% volume change —
comfortably past drift's 1e-4 threshold — moved only 542 pixels, well under
the 2400-pixel limit. The committed thumbnail would have gone quietly stale
while drift correctly reported the geometry had moved, and repeated small
changes would accumulate.

The failure modes are asymmetric, which settles it. Exact comparison fails
loudly and self-resolvingly: the instruction is "commit the regenerated file",
which is what a developer would do anyway. A tolerance fails silently and
permanently. If PNG rendering ever does become unstable, the fix is a *small*
tolerance calibrated to observed noise — not a large one chosen defensively
against a hypothetical.

#### That contingency has now fired

Rendered PNGs are reproducible **per host**, not across hosts. The fifteen
regenerations above all ran on one machine, which is exactly the case that
stays byte-identical.

Measured on `fred-drawer-pens-front`, whose thumbnail passed locally and failed
on CI:

- **Thirteen of fourteen** thumbnails were byte-identical between the
  devcontainer and the GitHub runner — including six other parts built from
  the same library module at other camera angles.
- The fourteenth differed by **one pixel** of 480,000, at (709, 346): the
  silhouette corner where the dovetail tab's top face meets the body's side
  face at equal depth. Local rendered it `srgb(24,59,61)`, CI
  `srgb(62,154,160)` — the two faces, not two shades of one. Every
  neighbouring pixel agreed.
- Three consecutive local renders were byte-identical to each other *and* to
  the committed file. Same pinned digest on both sides, reached the same way
  (`pr.yml` has no `container:`), same generated command, same camera.

So this is a depth tie broken differently by different CPUs, not the
tessellation instability originally feared. The earlier finding stands
unaltered: rasterizing at 800×600 does not surface vertex-level variation.

Getting that evidence needed a change of its own. `make -B` overwrites the
committed PNGs in place, so the runner held the only artifact that could
settle it and then discarded it — and a difference that exists only on the
runner's CPU cannot, by construction, be reproduced on the machine trying to
diff it. `pr.yml` now uploads the regenerated tree as an artifact when the
check fails.

The tolerance is **50 pixels**, calibrated rather than picked:

| | pixels |
|---|---|
| Cross-host disagreement, measured | 1 |
| **Threshold** | **50** |
| 0.62% volume change — the case that sank the original proposal | 542 |
| 0.1 mm wall thickness change | 905 |

Fifty is fifty times the observed noise and an order of magnitude below the
smallest real change on record. Critically it **still fails the 542-pixel
case**, which is the precise failure that defeated the earlier design: the
objection was to a tolerance of 2400 pixels chosen defensively, not to the
existence of a tolerance. The asymmetry argument above is what keeps the
number this small — a tolerance fails silently, so it has to sit close enough
to zero that anything real trips it.

## CI

All workflows run against the pinned toolchain image — see
[openscad-image.md](openscad-image.md) for exactly how a workflow reaches
it, which is not via GitHub Actions' `container:` key — check out with
`submodules: recursive`, and declare minimal `permissions:`.

### On every PR — build everything

Full builds, not incremental. Incremental is a premature optimization at this
scale, and the full build buys regression detection: a tweak to
`lib/krelinga/rounded_box.scad` that silently changes twelve parts is surfaced
rather than hidden.

1. `make check` — catalog validation.
2. Build all parts and all variants (`make -j`).
3. Per-mesh assertions: watertight, consistent winding, volume > 0, facets > 0.
   A zero-volume or empty result is a build failure, not a small file.
4. Regenerate thumbnails; verify the committed ones are fresh (above).
5. Diff metrics against each part's most recent release; post the summary as a
   PR comment.
6. Upload the whole `out/` tree as an Actions artifact.

**The metrics comment never fails the check.** Steps 1–4 are pass/fail: a broken
catalog, a build error, a non-manifold mesh, or a stale thumbnail all block the
merge, because each is unambiguously wrong. Step 5 is not — a changed volume is
information, and whether it is acceptable is a judgement made by whoever
approves the PR, who has the comment in front of them at that moment.

No threshold could make that judgement instead. Any number large enough not to
fire on routine work would be too large to catch the interesting cases, and the
cost of a false positive here is blocking a correct change. The information
reaching the reviewer is the whole requirement, and a comment satisfies it.

Revisit only if a real geometry regression turns out to have been merged past a
comment that described it accurately.

**Cost bound.** If the full build exceeds ~10 minutes, cache `out/` keyed on
`hash(image digest + parts/ + lib/)` before reaching for incremental make — a
whole-tree cache key has no correctness risk, whereas incremental rebuilds
depend on the dep files being complete, which they are not.

### What drift detection is for

Drift detection exists to answer one question: **is any part's declared version
still an honest description of what that part builds?**

It is not a correctness check. A part can drift and be perfectly fine — that is
the normal outcome of improving a shared module. Drift is a bookkeeping fact,
and the only thing it ever asks for is a decision about whether to re-tag.

That framing settles both its scope and its timing:

- **Scope: declared-version honesty, nothing else.** Whether the geometry is
  *good* is the PR reviewer's job, helped by the thumbnail diff. Whether the mesh
  is *valid* is the per-mesh assertion's job, and that one does fail the build.
  Drift only compares "what does the catalog claim" against "what came out."
- **Timing: it runs after merge, on `main`.** The PR already posts the same
  metrics diff as a comment, computed against the same baseline — the merge-time
  run is not discovering anything new. It is converting an observation into
  durable state.

Four reasons that conversion belongs after the merge rather than in the PR:

1. **A PR comment is not a to-do.** Re-tagging is usually decided later, after
   several merges have accumulated. An issue is the only surface that survives
   to the moment that decision actually gets made; a closed PR thread is not.
2. **The drift usually cannot be resolved in the PR that causes it.** Fix
   `lib/krelinga/rounded_box.scad` for bracket's sake and twelve parts shift.
   Bumping twelve versions in that PR is wrong — several of those shifts do not
   warrant a release at all. Version bumps are release decisions, not merge
   decisions. Forcing them into the PR is the stricter alternative rejected
   below.
3. **Aggregation.** After three merges each touching `lib/`, a part has drifted
   once, cumulatively. One issue per part, updated in place, is the true
   picture; three PR comments are three partial ones.
4. **The PR's answer can be stale by merge time.** Two PRs that each pass alone
   can combine into a `lib/` change that moves geometry — the PR check saw a
   hypothetical merge, the `main` check sees the real tree. And if a release is
   cut while a PR is open, the PR compared against a baseline that has since
   moved.

What this costs: you learn about drift a few minutes after merge rather than
before. Since the action it prompts is a release decision you would not have
taken during review anyway, that is the right trade.

### On merge to `main` — drift detection

Diff metrics against each part's most recent release. For any part whose output
changed but whose `version` did not, open an issue listing the affected parts.
If an open drift issue already exists for that part, update it rather than
filing a second one.

This is the `lib/`-change case announcing itself. Re-tagging then becomes a
deliberate decision made with full information, rather than something to
remember.

**The image-bump case must not storm.** A toolchain digest change will move
metrics on nearly every part at once. `drift.py` compares the current image
digest against the `image` field of each baseline build record; if they differ,
it files **one** rebaseline issue for the repository — "toolchain moved from
`@sha256:9f2c…` to `@sha256:c41a…`; N parts show geometry change; review and
re-tag as needed" — instead of N per-part issues. Without this the first pin
bump buries the signal it was meant to produce.

Two more baseline edge cases, both non-errors: a part with no release yet is
reported as "unreleased, no baseline"; a part whose baseline release predates
the current metrics schema is reported as "baseline incomparable".

*Rejected stricter alternative:* fail the check instead of filing an issue,
forcing version bumps before merge. It keeps declared versions honest by
construction, but it puts a release decision on the critical path of every
shared-library change, and — per reason 2 above — that decision is frequently
"no bump needed," which the check has no way to express.

### On workflow_dispatch — release

Input: part name. Optional input: ref (defaults to `main`).

1. `make check`; ask `catalog.py` to resolve the part name to its directory;
   read `version` from its `entry.yaml`.
2. Refuse if tag `<name>/v<version>` already exists.
3. Clean full build of that part only, plus thumbnails.
4. Create and push the tag at the selected ref.
5. Attach: `.3mf` and `.stl` per variant, `build-record.json`,
   `<name>-v<version>-PRINT.md`, and `SHA256SUMS`.
6. Generate release notes from the metrics diff against the previous release of
   that part, not a flat commit log:
   `bracket (v2.2 → v2.3): volume +3.1%, bbox 40×40×20 → 40×40×22`
   For a first release, note that instead.
7. `gh release create --latest=false`. GitHub's "Latest" badge is repo-wide, so
   with interleaved per-part releases it would always be misleading. No part
   release claims it.
8. Regenerate the README index block and commit it to `main`.

### README index

`render_index.py` fills a marked block in `README.md`, leaving everything
outside the markers — including the hand-written **Build your own variant**
section — untouched:

```
<!-- BEGIN INDEX -->
### printer-mods

| Part | Version | Release | Thumbnail |
|---|---|---|---|
| spool-holder | 1.4 | [spool-holder/v1.4](…) | ![](thumbnails/spool-holder/spool-holder.png) |

### Uncategorized

| Part | Version | Release | Thumbnail |
|---|---|---|---|
| bracket | 2.3 | [bracket/v2.3](…) | ![](thumbnails/bracket/m5_short.png) |
<!-- END INDEX -->
```

One section per category directory, in path order, with uncategorized parts
last. This is where the category structure is actually cashed in — it is a
presentation detail everywhere else.

It is also the answer to release-page noise: the release list stays a raw
interleaved stream, and the README is the thing anyone actually reads.

## Formats

3MF primary, STL alongside. 3MF carries units, which removes the single most
common source of "why did this print at 1/25 scale". STL stays for the GitHub 3D
viewer and for older tooling. Both come from one render (above), so the second
format costs one `trimesh.export()`.

## `lib/`

Stays unversioned, pinned by commit, for now. Drift detection is what makes that
safe — a `lib/` change that moves geometry announces itself on merge rather than
being discovered on the print bed.

Third-party libraries (BOSL2) are git submodules pinned to a release tag, not
vendored copies, so the pin is legible in `git log`. `OPENSCADPATH` is set in
the image to point at `lib/`; how that reaches a local invocation is
[openscad-image.md](openscad-image.md)'s concern, not settled here.

If `lib/` grows enough to be reused across repositories, it becomes **its own
repository consumed as a submodule** — not an additional tag namespace inside
this one. A second tag namespace here would collide conceptually with the
per-part one for no benefit.

## Open decisions

None. Everything above is settled; what follows is a deliberate non-goal rather
than an unresolved question.

## Out of scope

### Assemblies

This design has no concept of an assembly — not a built `assembly.scad` that
positions several parts and renders them, and not hand-written documentation of
how a set of parts goes together. Both are deferred entirely.

The reason is that **a part can participate in more than one assembly**, and
those groupings need not line up with where the part sits under `parts/`. A
`2020-corner` bracket might appear in a workbench, a camera rig, and a shelf,
none of which is its natural shelf in the taxonomy. That makes the
part-to-assembly relationship many-to-many, and a directory tree cannot express
many-to-many: siting assemblies in the `parts/` hierarchy would force each part
into one arbitrary home, or duplicate it into several.

Half-modelling it — say, by letting a category directory carry assembly prose —
would work for the parts that happen to have exactly one assembly and quietly
mislead for the rest. Better to leave the concept absent than to ship a version
of it that cannot represent the normal case.

If assemblies are taken up in a later iteration, the shape worth considering is
a separate top-level construct that references parts **by name** rather than by
location. Part names are globally unique across the repository, which is exactly
the property a cross-cutting reference needs, and it is already guaranteed. An
assembly would then be free to name any set of parts regardless of where they
sit, and re-shelving a part would not disturb it.
