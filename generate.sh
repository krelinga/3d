#! /usr/bin/bash

set -e

mkdir -p stl/bases
openscad -o stl/bases/one_inch.stl scad/bases/one_inch.scad