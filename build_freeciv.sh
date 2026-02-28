#!/bin/bash
set -e
meson compile -C "$1"
printf '/* freeciv built */\n' > "$2"
