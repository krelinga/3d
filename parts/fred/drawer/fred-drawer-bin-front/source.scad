include <krelinga/defaults.scad>
include <krelinga/units.scad>
include <krelinga/drawer_organizer.scad>

// Storage bin, front-right of the drawer organizer (grid position R1).
//
// The right column is 5 inches wide and holds three 6-inch-deep bins, one per
// part -- so unlike the pen trays this is a single undivided box rather than a
// subdivided one. Same module, `cells = 1`.
//
// The drawer's front wall closes it in, so its only neighbours are the pen
// tray to its left and the bin behind it: a socket on -X for the tray's tab,
// and a tab on +Y for the bin behind.

/* [Footprint] */
// Full width of the right column
width = 5 * inch;
// One third of the drawer's 18-inch depth
depth = 6 * inch;

/* [Cells] */
// One bin fills the part; the column's three bins are three parts
cells = 1;

organizer_tray(width, depth, cells, tab_y = true, sock_x = true);
