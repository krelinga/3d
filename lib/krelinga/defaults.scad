// Tessellation defaults, pinned deliberately.
//
// $fa/$fs/$fn default to values baked into the OpenSCAD binary, so inheriting
// them means a toolchain bump can silently retessellate every curve in the
// repo -- which drift detection would then report as a geometry change on
// every part at once. Setting them here makes tessellation a property of the
// source, not of the snapshot. See docs/design/initial-design.md, "Also pin
// $fa / $fs / $fn explicitly".
//
// $fn dominates $fa/$fs when set; the latter two are pinned anyway so that a
// part which deliberately overrides $fn to 0 gets a known fallback rather than
// whatever the binary ships.
$fn = 100;
$fa = 1;
$fs = 0.4;
