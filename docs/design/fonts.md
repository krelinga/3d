# Fonts in models

Status: implemented — `tools/check_fonts.py`, wired into `make check` and CI
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
   and nothing would say so. Enforceable: an omitted `font=` exports as
   `font = ""`, so the check can see it.

2. **Use only families the image ships.** The table above lists them, but that
   table is documentation, not the gate — rule 3 enforces this by measurement,
   so a family the image lacks fails whether or not anyone updated a list.

3. **CI must verify the font exists**, because nothing else will.

4. **Record the expected default** so a pin bump that changes it is caught
   rather than absorbed.

## How the check works

The check is two stages: **ask OpenSCAD which fonts a part requests, then
prove each one actually resolves.**

### Stage 1 — extraction, via CSG export

`openscad --export-format csg -o -` prints the evaluated CSG tree to stdout,
and `text()` appears in it with every argument filled in:

```
$ openscad --export-format csg -o - part.scad
linear_extrude(height = 2, ...) {
    text(text = "A", size = 8, font = "DejaVu Serif", ...);
}
```

**This is evaluated, not parsed.** All three of these report their resolved
value, which no amount of regexing the source would get right:

```scad
font = str(family, " ", weight)      ->  "DejaVu Serif"
font = pick(1)                       ->  "Liberation Sans"     // function + conditional
module labelled(f) ...; labelled("DejaVu Sans Mono")
                                     ->  "DejaVu Sans Mono"    // module parameter
```

Two properties fall out of this that source-parsing would not have given:

- **Omitting `font=` is visible.** It exports as `font = ""`, so rule 1 —
  never rely on the default — becomes something the check can enforce rather
  than something the doc merely asks for.
- **Only instantiated geometry is reported.** CSG is the evaluated tree, so a
  `text()` in a branch that was not taken does not appear. That is the right
  scope: the check should care about fonts a part actually uses.

It is also effectively free. CSG export of the drawer-pull jig took 0.200 s
against 0.203 s for a full 3MF render — both dominated by container startup,
so extraction costs nothing measurable.

Because a `params.json` parameter set could select a different font — or a
different string — extraction runs per part *per variant*, with the same
`-p`/`-P` the build uses, and yields (text, font) pairs rather than bare font
names. Stage 2 needs the text as much as the name.

### Stage 2 — does this text render in this font?

Extraction reports what was *asked for*, not what happened: a bogus name
exports as itself. So each name is rendered and compared against a
deliberately bogus control — the same string, with a font name that certainly
does not exist. **Identical geometry means the request fell back.**

The control renders **once per distinct string**, not once per font name: the
fallback does not depend on which font was requested.

**The control renders the part's own text, not a fixed sample**, and the
distinction turns out to matter:

```
text("A", font = "DejaVu Serif")      10.2465 x 10.1248, 58.1001 mm3   <- differs
text("A", font = "__no_such_font__")   9.2090 x  9.5548, 55.0511 mm3

text("日", font = "Liberation Sans")   7.6289 x  9.5548, 33.2991 mm3   <- IDENTICAL
text("日", font = "__no_such_font__")  7.6289 x  9.5548, 33.2991 mm3
```

Liberation Sans *is* installed, but it has no glyph for `日`, so it renders the
same `.notdef` box the fallback does. A fixed `"A"` control would have called
this font present and moved on, while the part quietly prints an empty box.

That is why the check is framed as **"does this text render in this font?"**
rather than "is this font installed?". The second question is easier and is
not the one that matters: a part is broken by a glyph it cannot draw just as
surely as by a font it cannot find, and the same measurement catches both.

The failure message must therefore describe the symptom rather than guess the
cause — *"`日` does not render in Liberation Sans; output is identical to the
fallback"* covers a missing font and a missing glyph without claiming to know
which.

### The fallback font is a blind spot, and rule 4 is why

Implementing this surfaced a limit the design did not anticipate. The check
recognises a failure *by its resemblance to the fallback*, so the fallback font
is the one name it can never judge: asking for Liberation Sans and asking for
nonsense produce identical geometry, because the second resolves to the first.

No refinement of the comparison fixes this — it is not a matter of a better
control string or a tighter tolerance. Nothing about the resulting mesh
distinguishes "you got what you asked for" from "you got the default instead",
because in this one case they are the same mesh.

Rule 4 turns out to be the answer rather than a nicety. `check_fonts.py`
records the expected fallback (`EXPECTED_FALLBACK`), and:

- a request naming the fallback passes, having been shown to resolve;
- every other name is measured against it as before;
- and the recorded value is itself asserted once per run — if an unresolvable
  name stops rendering as `EXPECTED_FALLBACK`, a toolchain bump has moved the
  default, and the run fails rather than quietly measuring against the wrong
  baseline.

Two consequences worth stating plainly. Glyph coverage cannot be checked for
the fallback font specifically — a character it lacks renders as `.notdef`,
which is exactly what the control renders, so it looks correct. And the check
is therefore weakest for the font a part is most likely to reach for by
default, which is a further argument for rule 1 rather than a reason to relax
it.

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

### Settled

- **`font = ""` fails.** Relying on the default is a rule 1 violation and is
  treated as one. Nothing in the repo uses `text()` yet, so the cost of being
  strict is zero today and only grows later — which is the argument for
  deciding it now rather than after a part depends on the leniency.

## Consequence for parts

With the check in place, `text()` becomes safe to use, and the objection that
kept it out of `jig-drawer-pull-96mm-coupon` — where bores are indexed with
notches rather than printed numbers — no longer applies.

Whether to revisit that part is a separate decision. Notches stay legible under
a coat of paint, do not care about layer height, and cannot be misread if the
font substitutes; embossed text is easier to read at a glance but is small
enough that print quality matters. The workaround has merits of its own.
