include <krelinga/defaults.scad>
include <krelinga/units.scad>
include <krelinga/drawer_organizer.scad>

// Storage bin, back-right of the drawer organizer (grid position R3).
//
// The far corner: the drawer's back and right walls close two of its edges, so
// it is the only part of the six carrying no tabs at all. Sockets on -X and -Y
// receive the back pen tray and the middle bin, and it is therefore the last
// part to drop into place.

/* [Footprint] */
// Full width of the right column
width = 5 * inch;
// One third of the drawer's 18-inch depth
depth = 6 * inch;

/* [Cells] */
// One bin fills the part; the column's three bins are three parts
cells = 1;

organizer_tray(width, depth, cells, sock_x = true, sock_y = true);
