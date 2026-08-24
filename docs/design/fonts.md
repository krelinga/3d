# Fonts in models

Status: specified, not implemented — the availability check does not exist yet
Scope: using OpenSCAD's `text()` safely. What is pinned, what is deterministic,
and the one failure mode that no existing gate catches.

## Why this is its own doc

`text()` was avoided on the grounds that fonts were not pinned the way the rest
of the toolchain is (issue #8). Measuring it showed the premise was half wrong:
fonts already ship inside the pinned image, so
[openscad-image.md](openscad-image.md)'s machinery covers them with no changes
at all.

That leaves nothing for the toolchain-image doc to say, but it does not leave
nothing to decide — the real hazard turns out to be in how OpenSCAD *resolves*
a font name, which is a modelling concern rather than a packaging one. Hence a
separate doc.

## Fonts are already pinned, because they live in the image

Two sets ship inside the pinned digest, so they carry exactly the same
guarantee as the `openscad` binary itself:

| Source | Version | Families |
|---|---|---|
| Bundled by OpenSCAD | `Liberation-2.00.1` | Liberation Sans / Serif / Mono |
| Debian package | `fonts-dejavu-core 2.37-8` | DejaVu Sans / Serif / Sans Mono |

Nothing needs adding. A pin bump can change the set, which is exactly the
visibility digest-pinning exists to provide.

**Availability cannot be established with `fc-list`.** The two sets are
discovered differently: `fc-list` reports only the DejaVu families, because
OpenSCAD's font path does not include its own bundled directory — yet
`font = "Liberation Sans"` resolves anyway, since OpenSCAD loads that set
internally. Any check that trusts a font database will therefore be wrong
about half the available fonts.

## Rendering is deterministic

Three renders of the same string produced identical geometry
(`40.8145 × 10.3563 × 2 mm`, `206.743 mm³`, 1688 facets), with and without an
explicit `font=`.

The `Fontconfig error: No writable cache directories` warnings the container
emits are noise: the cache cannot be written because the shim runs as a
non-root user with no writable `HOME`. Rebuilding it each run costs
milliseconds and changes nothing measurable.

Text geometry is therefore no less reproducible than any other geometry — 3MF
bytes still vary run to run per upstream
[#4931](https://github.com/openscad/openscad/issues/4931), but the measured
geometry does not.

## The hazard: a missing font falls back silently

Naming a font is **not** self-verifying:

```
font = "Liberation Sans"   ->  40.8145 x 10.3563 x 2 mm, 206.743 mm3
font = "TotallyMadeUp"     ->  40.8145 x 10.3563 x 2 mm, 206.743 mm3
no font= at all            ->  40.8145 x 10.3563 x 2 mm, 206.743 mm3
```

A font that does not exist renders as the default, exits 0, and writes a
perfectly valid mesh. `--hardwarnings` does not catch it.

This matters more than it first appears. A typo, or a family removed by a pin
bump, produces a part whose text is silently in the wrong face — and because
the result is a sound manifold mesh with plausible dimensions, **every gate
this repo has passes it**: the catalog is valid, the per-mesh assertions in
`tools/metrics.py` pass, and drift reports nothing unless the substitution
happens to move the measured geometry.

Font *selection* itself works. The five available families each produce
distinctly different geometry; the failure is confined to *unavailable* names.

## Rules

1. **Name the font explicitly. Never rely on the default.** The default is
   currently Liberation Sans — identical geometry confirms it — but that is an
   observation about this digest, not a contract. A pin bump could change it
   and nothing would say so.

2. **Use only families the image ships.** The table above lists them, but that
   table is documentation, not the gate — rule 3 enforces this by measurement,
   so a family the image lacks fails whether or not anyone updated a list.

3. **CI must verify the font exists**, because nothing else will.

4. **Record the expected default** so a pin bump that changes it is caught
   rather than absorbed.

## How the check works

The check needs no font-enumeration API, which is fortunate given `fc-list`
cannot see the bundled set: **render the named font and a deliberately bogus
name, and compare the measured geometry. Identical means the named font is not
installed and fell back.**

That is the same measure-don't-trust approach the rest of this design uses —
`initial-design.md` compares geometry rather than hashing it, and
`tools/metrics.py` asserts on the mesh rather than trusting an exit code. Here
it tests what OpenSCAD actually did, rather than what a font database claims is
available.

Known limitation: a font that genuinely renders identically to the fallback
would be reported as missing. For distinct families that is not a realistic
case, and the alternative — trusting an enumeration that demonstrably cannot
see half the fonts — is worse.

### There is no allowlist to maintain

The obvious design is a list of permitted families, hard-coded or probed. Both
are unnecessary: because the check is *per name actually used*, naming a family
the image does not ship fails on its own. An allowlist would be a second,
staler statement of the same fact.

The table above therefore documents what is available; it does not gate
anything. A `--list` mode is still worth having so the answer to "what can I
use?" does not require reading a design doc, but it is a convenience, and it is
allowed to be incomplete in a way the gate is not — `fc-list` plus the bundled
directory is good enough for a human, and not good enough for a check.

### Font names live in the `.scad`, and only there

*Rejected: declaring fonts in `entry.yaml`.* It looks like it fits the design's
habit of making the catalog the single place to look, but it does not survive
contact with the check. Verifying a declaration means confirming it matches
what the source actually uses, which means parsing the `.scad` anyway — so the
declaration adds a second place for the name to live, a second place for it to
be wrong, and buys no verification that parsing did not already provide.

The catalog declares *intent that cannot be derived from the source*: a
version, a status, a camera. A font name is not that; it is already in the
source, unambiguously.

### Where it lives: `tools/check_fonts.py`, not `catalog.py`

`catalog.py` validates `entry.yaml` structure. This scans `.scad` sources and
renders geometry — different input, different mechanism, and a dependency on
the toolchain that catalog validation deliberately does not have. Bolting it on
would make `catalog.py` two tools sharing a name.

Makefile wiring follows the pattern `catalog-check` and `index-check` already
set: a narrow `fonts-check` target so a failing CI step is named for the
problem it found, rolled into `make check` alongside the others, and therefore
into `make pr`.

One wrinkle worth naming: `make check` is otherwise "everything CI can verify
without building", and this renders. It stays there anyway — `make check`
already requires the toolchain image to run `bin/python3` at all, so the
dependency is unchanged and only the runtime grows, by a couple of tiny renders
per distinct font name. A separate never-run target would be worse than a
slightly slower `make check`.

### Still open

- Whether the bogus-name control is rendered once per run or once per font.
  Once per run is faster and is almost certainly equivalent, since the fallback
  does not depend on what was asked for — but that is an assumption worth
  measuring before relying on it.
- What the check does about `text()` calls whose `font` is a variable or an
  expression rather than a literal. Refusing to guess and reporting them as
  unverifiable is probably right, but it needs deciding before the first part
  does it.

## Consequence for parts

With the check in place, `text()` becomes safe to use, and the objection that
kept it out of `jig-drawer-pull-96mm-coupon` — where bores are indexed with
notches rather than printed numbers — no longer applies.

Whether to revisit that part is a separate decision. Notches stay legible under
a coat of paint, do not care about layer height, and cannot be misread if the
font substitutes; embossed text is easier to read at a glance but is small
enough that print quality matters. The workaround has merits of its own.
