#! /usr/bin/bash

set -e

OUT_BASE="/nas/dev/3d"

mkdir -p $OUT_BASE/stl/bases
openscad -o $OUT_BASE/stl/bases/one_inch.stl scad/bases/one_inch.scad