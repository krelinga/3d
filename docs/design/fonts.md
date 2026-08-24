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

2. **Use only families the image ships**, i.e. the table above. Anything else
   silently becomes the default.

3. **CI must verify the font exists**, because nothing else will.

4. **Record the expected default** so a pin bump that changes it is caught
   rather than absorbed.

## How the check works

Rule 3 needs no font-enumeration API, which is fortunate given `fc-list`
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

### Open questions

- Where the check lives. It needs to scan `.scad` sources for `font =` values,
  which is a different shape of work from `tools/catalog.py`'s `entry.yaml`
  validation, and it needs to *render* something, which `make check` currently
  never does.
- Whether the allowlist is hard-coded or derived by probing the image.
- Whether a part may use a font at all without declaring it in `entry.yaml`.
  Declaring it would make the catalog the single place to look, consistent with
  how the rest of the design treats declared intent — at the cost of a name
  appearing in two places, which the catalog design otherwise avoids.

## Consequence for parts

With the check in place, `text()` becomes safe to use, and the objection that
kept it out of `jig-drawer-pull-96mm-coupon` — where bores are indexed with
notches rather than printed numbers — no longer applies.

Whether to revisit that part is a separate decision. Notches stay legible under
a coat of paint, do not care about layer height, and cannot be misread if the
font substitutes; embossed text is easier to read at a glance but is small
enough that print quality matters. The workaround has merits of its own.
