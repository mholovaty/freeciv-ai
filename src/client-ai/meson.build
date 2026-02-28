# Dependencies
audio_dep = dependency('SDL2_mixer', required: false)
net_dep = dependency('libcurl', required: false)
gettext_dep = dependency('gettext', required: false)
lua_dep = dependency(
  'lua5.4', 'lua-5.4', 'lua54', 'lua5.3', 'lua-5.3', 'lua53', 'lua', required: false)
m_dep = meson.get_compiler('c').find_library('m', required: false)
readline_dep = meson.get_compiler('c').find_library('readline', required: true)
cairo_dep = dependency('cairo', required: false)

# freeciv build output is in builddir/freeciv (relative to build root)
executable('freeciv-client-ai',

  freeciv_build,
  'canvas.c',
  'dialogs.c',
  'diplodlg.c',
  'gui_callbacks.c',
  'gui_main.c',
  'optiondlg.c',
  'repodlgs.c',
  'sprite.c',

  '../../freeciv/client/gui_cbsetter.c',
  '../../freeciv/client/gui_interface.c',
  '../../freeciv/client/gui-stub/chatline.c',
  '../../freeciv/client/gui-stub/citydlg.c',
  '../../freeciv/client/gui-stub/cityrep.c',
  '../../freeciv/client/gui-stub/colors.c',
  '../../freeciv/client/gui-stub/connectdlg.c',
  '../../freeciv/client/gui-stub/finddlg.c',
  '../../freeciv/client/gui-stub/gotodlg.c',
  '../../freeciv/client/gui-stub/graphics.c',
  '../../freeciv/client/gui-stub/helpdlg.c',
  '../../freeciv/client/gui-stub/infradlg.c',
  '../../freeciv/client/gui-stub/inteldlg.c',
  '../../freeciv/client/gui-stub/luaconsole.c',
  '../../freeciv/client/gui-stub/mapctrl.c',
  '../../freeciv/client/gui-stub/mapview.c',
  '../../freeciv/client/gui-stub/menu.c',
  '../../freeciv/client/gui-stub/messagedlg.c',
  '../../freeciv/client/gui-stub/messagewin.c',
  '../../freeciv/client/gui-stub/pages.c',
  '../../freeciv/client/gui-stub/plrdlg.c',
  '../../freeciv/client/gui-stub/ratesdlg.c',
  '../../freeciv/client/gui-stub/spaceshipdlg.c',
  '../../freeciv/client/gui-stub/themes.c',
  '../../freeciv/client/gui-stub/voteinfo_bar.c',
  '../../freeciv/client/gui-stub/wldlg.c',

  include_directories: [
    '../../freeciv/client',
    '../../freeciv/client/include',
    '../../freeciv/client/gui-stub',
    '../../freeciv/client/luascript',
    '../../freeciv/client/agents',
    '../../freeciv/common',
    '../../freeciv/common/aicore',
    '../../freeciv/common/networking',
    '../../freeciv/common/scriptcore',
    '../../freeciv/utility',
    '../../freeciv/dependencies/luasql/src',
    '../../freeciv/dependencies/tinycthread',
    '../../freeciv/dependencies/tolua-5.2/include',
    '../../freeciv/dependencies/cvercmp',
  ],

  c_args: [
    '-Wno-error',
    '-DHAVE_CONFIG_H',
    '-I' + freeciv_builddir_path,
  ],

  link_args: [
    '-L' + freeciv_builddir_path,
    '-lfc_client_common',
    '-lfreeciv',
  ],

  dependencies: [audio_dep, net_dep, gettext_dep, lua_dep, m_dep, readline_dep, cairo_dep],

  install: true,
  build_rpath: freeciv_builddir_path,
  build_by_default: true
)
