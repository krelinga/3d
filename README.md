# 3d

OpenSCAD sources for 3D-printable parts.

**Meshes are build output, not source.** Nothing under `out/` is committed —
CI builds every part on each pull request, and releases carry the `.3mf` and
`.stl` as assets, the same way a compiled binary would be. This removes the
usual failure mode where someone edits a `.scad` and forgets to re-export,
leaving source and mesh silently disagreeing.

## Downloading a part

Grab the `.3mf` (or `.stl`) from that part's release — see the index below.
Each release also carries a `PRINT.md` with suggested print settings, a
`build-record.json` recording exactly what produced it, and `SHA256SUMS`.

Prefer the **3MF**: it carries units, which removes the most common cause of
a model printing at 1/25 scale. The STL is there for the GitHub 3D viewer and
older tooling.

## Building locally

The toolchain is a container image pinned by digest, so a local build and a CI
build are the same claim rather than two similar ones. You need Docker; you do
**not** need OpenSCAD installed.

```sh
make             # build every part: 3mf + stl + metrics
make check       # validate the catalog
make thumbnails  # re-render the committed review images
make -j$(nproc)  # parts are independent; OpenSCAD is single-threaded per run
```

`bin/openscad` and `bin/python3` run inside the pinned image, so `make` needs
nothing else installed. See `docs/design/openscad-image.md`.

## Previewing while you work

For a live, rotatable preview that re-renders as you save:

```sh
node viewer/server.mjs one-inch
```

then open the forwarded port. See `docs/design/previews.md`.

## Build your own variant

The variants listed below are a curated set — builds someone decided were
worth standing behind — not an exhaustive one. Anything else, build yourself:
`params.json` is an ordinary OpenSCAD customizer file, so a part opens in the
GUI with its parameter sets populated, and the CLI path is the same one CI
uses.

```sh
./bin/openscad --backend=manifold \
    -D some_parameter=6 \
    -o my-variant.3mf parts/bases/one-inch/source.scad
```

Nothing in the repo needs to change to support that, which is why the blessed
list stays curated rather than becoming a parameter-space matrix. If a size
turns out to be worth standing behind, add a `param_set` to `params.json` and
a `variants:` entry to `entry.yaml`.

## Design

- `docs/design/initial-design.md` — repo structure, catalog, versioning,
  build, CI, releases
- `docs/design/openscad-image.md` — how the pinned toolchain image is built
  and reached
- `docs/design/previews.md` — the live preview loop

## Parts

<!-- BEGIN INDEX -->
### bases

| Part | Version | Description | Release | Thumbnail |
|---|---|---|---|---|
| `40mm-heavy` | 1.0 | Large round miniature base with a wide recess for a weight or magnet (radius 40mm, i.e. 80mm across) | [40mm-heavy/v1.0](https://github.com/krelinga/3d/releases/tag/40mm-heavy%2Fv1.0) | ![40mm-heavy](thumbnails/40mm-heavy/40mm-heavy.png) |
| `four-fifths-inch` | 1.0 | Four-fifths-inch round miniature base with a shallow centre recess | [four-fifths-inch/v1.0](https://github.com/krelinga/3d/releases/tag/four-fifths-inch%2Fv1.0) | ![four-fifths-inch](thumbnails/four-fifths-inch/four-fifths-inch.png) |
| `one-inch` | 1.0 | One-inch round miniature base with a shallow centre recess | [one-inch/v1.0](https://github.com/krelinga/3d/releases/tag/one-inch%2Fv1.0) | ![one-inch](thumbnails/one-inch/one-inch.png) |
| `one-inch-heavy` | 1.0 | One-inch round miniature base with a wide recess for a weight or magnet | [one-inch-heavy/v1.0](https://github.com/krelinga/3d/releases/tag/one-inch-heavy%2Fv1.0) | ![one-inch-heavy](thumbnails/one-inch-heavy/one-inch-heavy.png) |
| `two-inch-heavy` | 1.0 | Two-inch round miniature base with a wide recess for a weight or magnet | [two-inch-heavy/v1.0](https://github.com/krelinga/3d/releases/tag/two-inch-heavy%2Fv1.0) | ![two-inch-heavy](thumbnails/two-inch-heavy/two-inch-heavy.png) |
<!-- END INDEX -->
