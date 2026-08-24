include <krelinga/defaults.scad>
include <krelinga/units.scad>

// DELIBERATELY BROKEN: two discs placed exactly tangent, so they meet along a
// single zero-width edge. The result is non-manifold -- it has no consistent
// inside along that seam -- but OpenSCAD renders it, writes the file and exits
// 0, with or without --hardwarnings. tools/metrics.py is the only guard.
cylinder(h = inch * 1/8, r = .8 * inch * 1/2);
translate([.8 * inch, 0, 0])
    cylinder(h = inch * 1/8, r = .8 * inch * 1/2);
