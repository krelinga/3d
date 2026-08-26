include <krelinga/defaults.scad>
include <krelinga/units.scad>
include <krelinga/drawer_organizer.scad>

// Dovetail fit coupon for the drawer organizer.
//
// The organizer has seven seams across six parts, and every one of them uses
// the same dovetail at the same clearance. That makes dove_fit a single number
// that is either right everywhere or wrong everywhere -- and you would not
// find out which until roughly a kilogram of filament had already gone into
// the trays. So measure it here first.
//
// A printed socket comes out undersize and a printed tab oversize, by an
// amount set by extrusion width, shrinkage and elephant's foot rather than by
// the model. This prints one tab and a row of sockets stepped either side of
// nominal; slide the tab into each and let the joint pick the winner.
//
// Read the notches, not the position: socket i carries i+1 of them, so the row
// cannot be read backwards and a socket stays identifiable once broken off.
// Whichever seats snugly -- firm by hand, no mallet, no rock -- names what
// dove_fit should be in lib/krelinga/drawer_organizer.scad.
//
// The centre socket tracks the CURRENT dove_fit, not zero clearance. Before
// calibration those differ. Afterwards, re-printing this is a confirmation --
// the centre should now win -- rather than a fresh measurement. Picking an
// offset socket a second time means ADJUSTING dove_fit by that step, not
// adding another one to it.
//
// Tab geometry and slab thickness come from the shared file, so the coupon
// always tests the organizer's real joint rather than a stale copy of it.
//
// PRINT IT THE SAME WAY AS THE TRAYS -- flat on the bed, dovetails vertical.
// The undercut's dimensional error is a layer-adhesion effect, so a coupon
// printed on its side would be measuring a different joint.

/* [Fits] */
// How many sockets. Set to 1 for a plain single-socket coupon at nominal.
fit_count = 5;
// Clearance difference between adjacent sockets
step = 0.1;
// Centre socket -- shared with the trays
nominal_fit = dove_fit;

/* [Blocks] */
// Material either side of the socket mouth
margin = 6;
// Material behind the socket
backing = 8;
// Gap between adjacent blocks
gutter = 4;

/* [Index notches] */
notch_w = 1.6;
notch_depth = 2;
notch_pitch = 3.2;

block_w = dove_tip + 2 * margin;
block_d = dove_len + backing;
spacing = block_w + gutter;
row_w = (fit_count - 1) * spacing + block_w;

function fit(i) = nominal_fit + step * (i - (fit_count - 1) / 2);
function block_x(i) = i * spacing;

// Sockets, tightest on the left.
for (i = [0 : fit_count - 1])
    translate([block_x(i), 0, 0]) difference() {
        cube([block_w, block_d, org_platform]);
        translate([block_w / 2, 0, 0]) dove_socket(fit(i));

        // Notches on the back edge, clear of the socket.
        for (j = [0 : i])
            translate([block_w / 2 - i * notch_pitch / 2
                         + j * notch_pitch - notch_w / 2,
                       block_d - notch_depth, -1])
                cube([notch_w, notch_depth + 1, org_platform + 2]);
    }

// The tab, on its own block, set in front of the row and pointing at it.
tab_block_d = 12;
translate([row_w / 2 - block_w / 2, -(tab_block_d + dove_len + gutter), 0]) {
    cube([block_w, tab_block_d, org_platform]);
    translate([block_w / 2, tab_block_d, 0]) dove_tab();
}

for (i = [0 : fit_count - 1])
    echo(str("socket ", i + 1, ": fit ", fit(i), " mm  (nominal ",
             step * (i - (fit_count - 1) / 2) >= 0 ? "+" : "",
             step * (i - (fit_count - 1) / 2), ")"));
