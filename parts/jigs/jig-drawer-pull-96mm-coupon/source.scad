include <krelinga/defaults.scad>
include <krelinga/units.scad>
include <krelinga/drawer_pull_jig.scad>

// Press-fit test coupon for jig-drawer-pull-96mm.
//
// Printed holes rarely come out at their modelled diameter -- extrusion width,
// shrinkage and elephant's foot all pull them undersize, by an amount that
// depends on the printer and filament rather than on the model. For a press
// fit that matters: too tight splits the plate, too loose lets the bushing
// walk under drilling load, and either way you find out after committing
// ~150 g of filament to the full jig.
//
// So this prints a row of bores stepped either side of nominal and lets the
// bushing pick the winner. Whichever seats correctly tells you what to set
// jig_hole_dia to in lib/krelinga/drawer_pull_jig.scad.
//
// Thickness and nominal diameter come from that same shared file, so the
// coupon always tests the jig's real bore rather than a stale copy of it.
//
// PRINT IT THE SAME WAY AS THE JIG -- flat on the bed, bores vertical. A bore
// printed on its side has completely different dimensional error, and would
// make this test misleading rather than merely useless.

/* [Bores] */
// How many test bores. Set to 1 for a plain single-hole coupon at nominal.
hole_count = 5;
// Diameter difference between adjacent bores
step = 0.15;
// Bore centre spacing
spacing = 16;
// Nominal bore -- shared with the jig
nominal_dia = jig_hole_dia;
// Slab thickness -- shared with the jig, because bore depth drives press-fit
// friction just as much as diameter does
thickness = jig_plate;

/* [Slab] */
// Material beyond the outermost bore centres
margin = 9;
// Front to back
depth = 28;

/* [Index notches] */
// Bore i carries i+1 notches, so a bore can be identified without counting
// from an end -- and the coupon cannot be read backwards.
notch_w = 1.6;
notch_depth = 2;
notch_pitch = 3.2;

width = (hole_count - 1) * spacing + 2 * margin;
// Puts the same 10.7 mm of material below each bore that the jig has below
// its own, so the surrounding material behaves comparably.
hole_y = depth - 12;

function dia(i) = nominal_dia + step * (i - (hole_count - 1) / 2);
function hole_x(i) = margin + i * spacing;

difference() {
    cube([width, depth, thickness]);

    // Graduated bores, smallest on the left.
    for (i = [0 : hole_count - 1])
        translate([hole_x(i), hole_y, -1])
            cylinder(h = thickness + 2, d = dia(i));

    for (i = [0 : hole_count - 1])
        for (j = [0 : i])
            translate([hole_x(i) - i * notch_pitch / 2
                         + j * notch_pitch - notch_w / 2, -1, -1])
                cube([notch_w, notch_depth + 1, thickness + 2]);
}

for (i = [0 : hole_count - 1])
    echo(str("bore ", i + 1, ": ", dia(i), " mm  (nominal ",
             step * (i - (hole_count - 1) / 2) >= 0 ? "+" : "",
             step * (i - (hole_count - 1) / 2), ")"));
