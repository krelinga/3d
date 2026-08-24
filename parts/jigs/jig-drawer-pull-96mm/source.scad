include <krelinga/defaults.scad>
include <krelinga/units.scad>
include <krelinga/drawer_pull_jig.scad>

// Drilling jig for a 96 mm centre-to-centre drawer pull.
//
// The lip hooks over the top edge of the drawer face, so the jig registers off
// that edge every time and every drawer gets identically placed holes. Hole
// positions are measured from the lip's underside -- the surface that actually
// touches the drawer -- not from the top of the jig, so `hole_drop` is the
// real distance from the drawer's top edge to the pull centres.
//
// The holes take press-fit steel bushings; the drill bit rides in hardened
// steel rather than in plastic, which is what keeps the hole from wandering
// and the jig from wearing out after a few drawers.

/* [Overall] */
// Left to right
width = 6 * inch;
// Top to bottom, including the lip
height = 3 * inch;
// Face plate thickness -- match your bushing length so they sit flush.
// Shared with the fit coupon, which is only meaningful at the same thickness.
plate = jig_plate;

/* [Lip] */
// How far the lip reaches back over the top of the drawer face
lip_depth = 1/2 * inch;
// Lip thickness
lip = 3/8 * inch;

/* [Bushing holes] */
// Centre-to-centre, set by the pull
hole_spacing = 96;
// Bushing outside diameter. Shared with the fit coupon so a change to one
// cannot leave the other testing the wrong size.
hole_dia = jig_hole_dia;
// Drawer's top edge down to the hole centres
hole_drop = 2 * inch;

// The lip's underside: where the drawer's top edge sits, and the datum every
// hole position is measured from.
datum_z = height - lip;
hole_z = datum_z - hole_drop;

difference() {
    union() {
        // Face plate: lies flat against the drawer front.
        cube([width, plate, height]);
        // Lip: projects back across the top edge of the drawer face.
        translate([0, -lip_depth, datum_z])
            cube([width, lip_depth, lip]);
    }
    // Bushing bores, straight through the face plate.
    for (side = [-1, 1])
        translate([width / 2 + side * hole_spacing / 2, -1, hole_z])
            rotate([-90, 0, 0])
                cylinder(h = plate + 2, d = hole_dia);
}
