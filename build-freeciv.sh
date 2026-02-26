#!/bin/bash
set -e

mkdir -p builddir/freeciv

cd builddir/freeciv
meson setup . ../../freeciv -Dclients=stub -Dfcmp=cli -Dtools='[]'

meson compile

echo "Freeciv build complete!"
