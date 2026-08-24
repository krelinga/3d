include <krelinga/units.scad>

// Dimensions shared between jig-drawer-pull-96mm and jig-drawer-pull-96mm-coupon.
//
// The coupon exists to predict how a bushing will seat in the jig. That
// prediction is only worth anything if both bores are identical -- same
// diameter AND same depth, since the depth sets how much interference surface
// the press fit has to overcome. Declaring them once means the coupon cannot
// quietly stop representing the jig.

// Bushing bore. Match your bushings' actual measured OD.
jig_hole_dia = 13/32 * inch;

// Face plate thickness, which is also the bore depth. A measured value, not
// a derived one -- it comes from the bushings themselves, so it is written as
// the measurement rather than as 3/8" (9.525 mm), which it is close to but is
// not. Re-measure before changing it.
jig_plate = 9.52;
