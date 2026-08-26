include <krelinga/defaults.scad>
include <krelinga/units.scad>
include <krelinga/drawer_organizer.scad>

// Pen tray, front-left of the drawer organizer (grid position L1).
//
// One of six parts that tile an 11 x 18 x 2 inch drawer interior. The left
// column is 6 inches wide and holds twelve 1.5-inch pen cells; this part
// carries the first four of them.
//
// Corner part, so it is the simplest of the six: the drawer's own front and
// left sides close it in, and the only neighbours are the next tray back and
// the bin to its right. Both of those sit at greater Y and greater X, so by
// the seam convention in drawer_organizer.scad this part is all tabs and no
// sockets. See that file for why the joint is a dovetail.

/* [Footprint] */
// Full width of the left column
width = 6 * inch;
// One third of the drawer's 18-inch depth
depth = 6 * inch;

/* [Cells] */
// 1.5-inch pen cells: a quarter of the twelve in the left column
cells = 4;

organizer_tray(width, depth, cells, tab_x = true, tab_y = true);
