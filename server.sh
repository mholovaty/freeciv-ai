#!/bin/bash

SAVES=$(mktemp -d)
trap 'rm -rf "$SAVES"' EXIT

FREECIV_DATA_PATH="$PWD/freeciv/data" \
exec ./builddir/freeciv/freeciv-server \
  -p 5556 \
  -r tiny.serv \
  -e \
  -q 60 \
  --saves "$SAVES"
