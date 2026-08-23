include <krelinga/defaults.scad>
include <krelinga/units.scad>

difference() {
    cylinder(h = inch * 1/8, r = 40);
    cylinder(h = inch * 15/256, r = 1.1 * inch * 3/16);
}
