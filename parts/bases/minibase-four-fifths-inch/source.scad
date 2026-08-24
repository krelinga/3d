include <krelinga/defaults.scad>
include <krelinga/units.scad>

// DELIBERATELY BROKEN: the recess is larger than the body, so the
// difference() removes everything and the part builds to nothing.
difference() {
    cylinder(h = inch * 1/8, r = .8 * inch * 1/2);
    cylinder(h = inch, r = inch);
}
