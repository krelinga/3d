include <krelinga/defaults.scad>
include <krelinga/units.scad>
include <krelinga/drawer_organizer.scad>

// Pen tray, middle-left of the drawer organizer (grid position L2).
//
// The second of the three trays that make up the drawer's 6-inch-wide left
// column, carrying pen cells five through eight of the twelve.
//
// Unlike the front tray this one has a neighbour behind it AND in front of it,
// so it carries both halves of the joint: sockets on its -Y edge for the front
// tray's tabs, tabs on +Y for the back tray, and tabs on +X for the bin
// alongside. Three seams on one part is the case the dovetail was chosen for --
// see drawer_organizer.scad -- because all three engage on the same straight
// drop downward, which no push-together joint could manage.

/* [Footprint] */
// Full width of the left column
width = 6 * inch;
// One third of the drawer's 18-inch depth
depth = 6 * inch;

/* [Cells] */
// 1.5-inch pen cells: the second quarter of the twelve in the left column
cells = 4;

organizer_tray(width, depth, cells,
               tab_x = true, tab_y = true, sock_y = true);
