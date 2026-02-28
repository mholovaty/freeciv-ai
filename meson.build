project('freeciv-ai', 'c',
        meson_version: '>= 0.63.0',
        version: '1.0.0',
        default_options: ['warning_level=1'])

fs = import('fs')

freeciv_src     = meson.current_source_dir() / 'freeciv'
freeciv_builddir = meson.current_build_dir() / 'freeciv'

meson_prog = find_program('meson')

# Configure freeciv at meson setup time (once)
if not fs.exists(freeciv_builddir / 'build.ninja')
  run_command(
    meson_prog, 'setup', freeciv_builddir, freeciv_src,
    '-Dclients=stub', '-Dfcmp=cli', '-Dtools=',
    check: true)
endif

freeciv_build = custom_target('freeciv',
  output: 'freeciv_built.c',
  command: [
    'bash', meson.current_source_dir() / 'build_freeciv.sh',
    freeciv_builddir, '@OUTPUT@',
  ],
  build_always_stale: true,
  console: true,
)

subdir('src')
