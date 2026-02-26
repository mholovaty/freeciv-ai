project('freeciv-ai', 'c',
        meson_version: '>= 0.63.0',
        version: '1.0.0',
        default_options: ['warning_level=1'])

fs = import('fs')

freeciv_src = meson.current_source_dir() / 'freeciv'
freeciv_builddir = meson.current_build_dir() / 'freeciv'

if not fs.exists(freeciv_builddir / 'libfreeciv.so')
  error('Freeciv not built. Run: ./build-freeciv.sh')
endif

subdir('src')
