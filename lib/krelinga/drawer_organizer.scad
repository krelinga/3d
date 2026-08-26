// Drawer organizer: a grid of trays that tile one drawer and lock together.
//
// The drawer is bigger than the printer, so the organizer is split into a
// grid of parts that each print flat and then hook together in the drawer.
// Every part is a solid slab -- the platform -- with cell cavities cut down
// into it from above, plus dovetails in the LOWER PART of the platform that
// mate with its neighbours. The joint deliberately stops short of the platform
// top so that every cell keeps an unbroken floor; see dove_height.
//
// WHY DOVETAILS AND NOT PINS. The parts form a 2-wide by 3-deep grid, so an
// interior part has three neighbours. Any joint that assembles by pushing two
// parts together in the seam normal -- pins, snap hooks, a lap joint -- needs
// the middle part to travel toward its front and back neighbours at the same
// time, which it cannot. A trapezoidal dovetail extruded in Z has a constant
// cross-section, so it constrains both X and Y (the undercut stops pull-apart,
// the socket walls stop sliding along the seam) and leaves Z free. Every part
// therefore drops straight down into all of its neighbours at once. Gravity
// and the drawer sides hold Z; nothing needs to latch.
//
// SEAM CONVENTION. Tabs always point +X and +Y; sockets always face -X and -Y.
// Stated once here so no part has to reason about which half of a seam it
// owns: a part carries a tab on a seam if it has a neighbour at greater X or
// Y, and a socket if it has one at lesser X or Y. Getting this backwards on a
// single part is the one error that would not show up until six parts were
// printed, so it is a rule rather than a per-part decision.

// Shared across every part in the collection. Changing one of these changes
// the whole set, which is the point -- the parts only tile if they agree.
org_wall     = 1/8 * inch;   // between cells, and at every part edge
org_platform = 1/4 * inch;   // solid base: cell floor and dovetail stock
org_height   = 2 * inch;     // drawer's interior height

// Dovetail proportions. The tip is wider than the root -- that flare IS the
// undercut, and it is what makes the joint a joint rather than a peg.
dove_len  = 8;    // how far the tab reaches past the seam
dove_root = 10;   // width at the seam
dove_tip  = 16;   // width at the tip

// How tall the joint is, out of the platform's full 1/4 inch. Everything above
// it is solid floor.
//
// This is what keeps the cells' floors intact. A dovetail run through the full
// platform reaches 8 mm from the seam while the cell floor starts at one wall
// thickness -- 3.175 mm -- so the socket punched a 5 mm slot clean through the
// floor of the end cell, twice per socketed edge. Pens fall through that.
//
// So the socket is blind at the top and open only at the bottom, and the tab
// is the bottom dove_height of its part. Assembly is unchanged: the socketed
// part still comes straight down onto its neighbour's tab, which enters
// through the pocket's open underside. Closing the bottom as well would leave
// no way in at all -- the same reason a pin joint cannot work here.
dove_height = 4;
// Clearance per face between tab and socket, IN PLAN ONLY. FDM leaves the
// socket tight and the tab fat, so some is needed: a dovetail that needs a
// mallet is worse than one that needs a shim, because the drawer holds it
// captive anyway.
//
// Measured, not guessed. fred-drawer-dovetail-coupon printed the joint at five
// clearances; the tightest -- 0.0, one pip -- seated well and if anything a
// little loose, so nominal is where the printer lands. The coupon's centre
// socket tracks this value, so a re-print now sweeps -0.2 to +0.2 and will say
// whether an interference fit is better still.
dove_fit  = 0;

// Clearance above the tab, and NOT the same number as dove_fit.
//
// It used to be: the socket was extruded to dove_height + dove_fit, so one
// parameter set both the plan clearance and the roof height. That coupling is
// why the coupon's best-fitting socket was also the one that would not seat --
// at 0.0 plan clearance the roof landed at exactly the tab's top face, leaving
// nothing for the roof to sag into. It bridges over an open pocket, so it does
// sag, and the mortise bottomed out on the tenon before the parts were flush.
//
// Z clearance is close to free here, which is why this is generous. The roof
// carries no load and never needs to touch the tab: the dovetail's whole job
// is restraint in plan, and the trays sit on the drawer bottom, not on each
// other. All it costs is floor thickness above the socket -- 1.75 mm at these
// numbers, over the ~110 mm2 of each socket, against 1/4 inch everywhere else.
//
// 0.6 is three layers at the 0.2 mm layer height these print at, so the gap
// survives a sagging bridge and quantization instead of being consumed by it.
dove_z_fit = 0.6;

// Two dovetails per seam, not one: one tab is a pivot, and a pair 25% and 75%
// along the seam stops the parts hinging about it. Kept off the corners so
// that the tabs of two seams meeting at a corner cannot collide.
function dove_positions(span) = [span * 0.25, span * 0.75];

// The tab profile, pointing +Y with its root on the XY origin line.
module dove_profile() {
    polygon([
        [-dove_root / 2, 0], [dove_root / 2, 0],
        [ dove_tip  / 2, dove_len], [-dove_tip / 2, dove_len],
    ]);
}

module dove_tab() {
    linear_extrude(height = dove_height) dove_profile();
}

// The socket is the tab grown by the fit clearance on every face. It is cut
// from the -X or -Y edge, and the neighbour's tab enters pointing into this
// part -- so in this part's own frame the socket has exactly the tab's
// orientation, which is why tabs and sockets share the same rotation below.
// `fit` is the plan clearance only. The roof height comes from dove_z_fit and
// is deliberately independent of it -- see that constant for what conflating
// the two cost.
module dove_socket(fit = dove_fit) {
    // Sunk from below the underside so the cut is clean there, and stopped
    // short of the platform top so what remains above is unbroken floor.
    translate([0, 0, -1])
        linear_extrude(height = dove_height + dove_z_fit + 1) {
        offset(delta = fit) dove_profile();
        // Squares off the socket mouth so the cut reaches the part edge
        // cleanly even after the offset rounds nothing and moves the root to
        // -fit. Cheap insurance against a sliver of material at the seam.
        translate([-(dove_root / 2 + fit), -1])
            square([dove_root + 2 * fit, 1.5]);
    }
}

// One part of the organizer.
//
//   width, depth  the part's footprint, excluding any tabs
//   cells         how many cells it is divided into along Y
//   tab_x/tab_y   true if a neighbour sits at greater X / Y
//   sock_x/sock_y true if a neighbour sits at lesser X / Y
module organizer_tray(width, depth, cells,
                      tab_x = false, tab_y = false,
                      sock_x = false, sock_y = false) {
    // Cells share the interior evenly after every wall is taken out, so the
    // pitch falls out of the arithmetic rather than being declared and then
    // having to agree with the part size.
    cell_depth = (depth - org_wall * (cells + 1)) / cells;

    difference() {
        union() {
            cube([width, depth, org_height]);
            if (tab_y)
                for (p = dove_positions(width))
                    translate([p, depth, 0]) dove_tab();
            if (tab_x)
                for (p = dove_positions(depth))
                    translate([width, p, 0]) rotate([0, 0, -90]) dove_tab();
        }

        // Cell cavities, cut from the platform up and run past the top so the
        // rim is a cut face rather than a coincident one.
        for (k = [0 : cells - 1])
            translate([org_wall,
                       org_wall + k * (cell_depth + org_wall),
                       org_platform])
                cube([width - 2 * org_wall, cell_depth,
                      org_height - org_platform + 1]);

        if (sock_y)
            for (p = dove_positions(width))
                translate([p, 0, 0]) dove_socket();
        if (sock_x)
            for (p = dove_positions(depth))
                translate([0, p, 0]) rotate([0, 0, -90]) dove_socket();
    }
}
