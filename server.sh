#!/bin/bash

FREECIV_DATA_PATH="$PWD/freeciv/data" \
exec ./builddir/freeciv/freeciv-server \
  -p 5556 \
  -r tiny.serv \
  -e \
  -q 60
