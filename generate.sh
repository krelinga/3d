#! /usr/bin/bash

set -e

OUT_BASE="/nas/dev/3d"

mkdir -p $OUT_BASE/stl/bases
openscad -o $OUT_BASE/stl/bases/one_inch.stl scad/bases/one_inch.scad
openscad -o $OUT_BASE/stl/bases/four_fifths_inch.stl scad/bases/four_fifths_inch.scad
openscad -o $OUT_BASE/stl/bases/one_inch_heavy.stl scad/bases/one_inch_heavy.scad

echo "Generated STL files in $OUT_BASE/stl/bases"