include <krelinga/units.scad>

// Dimensions shared between jig-drawer-pull-96mm and jig-drawer-pull-96mm-coupon.
//
// The coupon exists to predict how a bushing will seat in the jig. That
// prediction is only worth anything if both bores are identical -- same
// diameter AND same depth, since the depth sets how much interference surface
// the press fit has to overcome. Declaring them once means the coupon cannot
// quietly stop representing the jig.

// The bushings' outside diameter, as supplied. A property of the hardware.
jig_bushing_od = 13/32 * inch;

// How much larger the modelled bore has to be for the PRINTED hole to come
// out at the bushing's size. A property of the printer and filament, not of
// the hardware, which is why it is separate: change the bushings and this
// still applies; change printer or material and it needs re-measuring.
//
// Measured with jig-drawer-pull-96mm-coupon: of the five graduated bores, the
// one carrying four hash marks -- nominal +0.15 mm -- was the best fit.
jig_bore_allowance = 0.15;

// What the model actually cuts.
jig_hole_dia = jig_bushing_od + jig_bore_allowance;

// Face plate thickness, which is also the bore depth. A measured value, not
// a derived one -- it comes from the bushings themselves, so it is written as
// the measurement rather than as 3/8" (9.525 mm), which it is close to but is
// not. Re-measure before changing it.
jig_plate = 9.52;
