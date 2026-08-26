include <krelinga/defaults.scad>
include <krelinga/units.scad>
include <krelinga/drawer_organizer.scad>

// Storage bin, middle-right of the drawer organizer (grid position R2).
//
// The centre of the right column, and the second of the two parts with three
// seams -- sockets on -X and -Y for the pen tray alongside and the bin in
// front, and a tab on +Y for the bin behind.

/* [Footprint] */
// Full width of the right column
width = 5 * inch;
// One third of the drawer's 18-inch depth
depth = 6 * inch;

/* [Cells] */
// One bin fills the part; the column's three bins are three parts
cells = 1;

organizer_tray(width, depth, cells,
               tab_y = true, sock_x = true, sock_y = true);
