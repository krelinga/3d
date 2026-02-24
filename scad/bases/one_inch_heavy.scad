inch = 25.4;
$fn = 100;

difference() {
    cylinder(h = inch * 1/8, r = inch * 1/2);
    cylinder(h = inch * 1/32, r = 1.1 * inch * 3/16);
}
