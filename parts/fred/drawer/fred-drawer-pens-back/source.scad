include <krelinga/defaults.scad>
include <krelinga/units.scad>
include <krelinga/drawer_organizer.scad>

// Pen tray, back-left of the drawer organizer (grid position L3).
//
// The last of the three trays in the drawer's 6-inch-wide left column,
// carrying pen cells nine through twelve of the twelve.
//
// Backs onto the drawer's rear wall, so there is no neighbour at greater Y and
// no tab on that edge -- the mirror of the front tray, which has no socket on
// its own outer edge for the same reason. What remains is sockets on -Y for
// the middle tray's tabs, and tabs on +X for the bin alongside.

/* [Footprint] */
// Full width of the left column
width = 6 * inch;
// One third of the drawer's 18-inch depth
depth = 6 * inch;

/* [Cells] */
// 1.5-inch pen cells: the last quarter of the twelve in the left column
cells = 4;

organizer_tray(width, depth, cells, tab_x = true, sock_y = true);
