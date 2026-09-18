include <krelinga/defaults.scad>
include <krelinga/units.scad>

difference() {
    cylinder(h = inch * 1/8, r = 32 * 1/2);
    cylinder(h = inch * 1/16, r = 1.25 * inch * 1/16);
}
