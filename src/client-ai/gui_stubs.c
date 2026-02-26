/* Comprehensive GUI callback stubs for headless client */

#ifdef HAVE_CONFIG_H
#include <fc_config.h>
#endif

#include <stdlib.h>
#include <stdbool.h>
#include <stddef.h>

/* utility */
#include "support.h"

/* common */
#include "fc_types.h"
#include "graphics_g.h"
#include "canvas_g.h"

/* client */
#include "gui_properties.h"
#include "tilespec.h"
#include "mapctrl_g.h"
#include "options.h"

/* Stub implementations */
enum gui_type gui_get_gui_type(void) { return GUI_STUB; }
void gui_insert_client_build_info(char *outbuf, size_t outlen) { }

/* Output functions */
void gui_version_message(const char *vertext) { }
void gui_real_output_window_append(const char *astring, const void *tags, int conn_id) { }

/* Sprite/Graphics functions */
struct sprite *gui_load_gfxfile(const char *filename, bool svgflag) { return NULL; }
struct sprite *gui_create_sprite(int width, int height, struct color *pcolor) { return NULL; }
void gui_get_sprite_dimensions(struct sprite *sprite, int *width, int *height) { }
struct sprite *gui_crop_sprite(struct sprite *source, int x, int y, int width, int height,
                               struct sprite *mask, int mask_offset_x, int mask_offset_y,
                               float scale, bool smooth) { return NULL; }
void gui_free_sprite(struct sprite *s) { }

/* Color functions */
struct color *gui_color_alloc(int r, int g, int b) { return NULL; }
void gui_color_free(struct color *pcolor) { }

/* Canvas functions */
struct canvas *gui_canvas_create(int width, int height) { return NULL; }
void gui_canvas_free(struct canvas *store) { }
void gui_canvas_set_zoom(struct canvas *store, float zoom) { }
bool gui_has_zoom_support(void) { return false; }
void gui_canvas_mapview_init(struct canvas *store) { }
void gui_canvas_copy(struct canvas *dest, struct canvas *src, int src_x, int src_y,
                     int dest_x, int dest_y, int width, int height) { }
void gui_canvas_put_sprite(struct canvas *pcanvas, int canvas_x, int canvas_y,
                           struct sprite *psprite, int offset_x, int offset_y,
                           int width, int height) { }
void gui_canvas_put_sprite_full(struct canvas *pcanvas, int canvas_x, int canvas_y,
                                struct sprite *psprite) { }
void gui_canvas_put_sprite_full_scaled(struct canvas *pcanvas, int canvas_x, int canvas_y,
                                       int canvas_w, int canvas_h, struct sprite *psprite) { }
void gui_canvas_put_sprite_fogged(struct canvas *pcanvas, int canvas_x, int canvas_y,
                                  struct sprite *psprite, bool fog, int fog_x, int fog_y) { }
void gui_canvas_put_rectangle(struct canvas *pcanvas, struct color *pcolor,
                              int canvas_x, int canvas_y, int width, int height) { }
void gui_canvas_fill_sprite_area(struct canvas *pcanvas, struct sprite *psprite,
                                 struct color *pcolor, int canvas_x, int canvas_y) { }
void gui_canvas_put_line(struct canvas *pcanvas, struct color *pcolor,
                         int ltype, int start_x, int start_y, int end_x, int end_y) { }
void gui_canvas_put_curved_line(struct canvas *pcanvas, struct color *pcolor,
                                int ltype, int start_x, int start_y, int end_x, int end_y) { }
int gui_get_text_size(int *width, int *height, int max_width,
                      int max_height, const char *text) { return 0; }
void gui_canvas_put_text(struct canvas *pcanvas, int canvas_x, int canvas_y,
                         int max_width, int max_height, int font, void *color,
                         const char *astring) { }

/* Map canvas functions */
void gui_map_canvas_size_refresh(void) { }

/* Ruleset/connection functions */
void gui_set_rulesets(int num_rulesets, const void *rulesets) { }
void gui_options_extra_init(void) { }
void gui_server_connect(void) { }
void gui_add_net_input(int sock) { }
void gui_remove_net_input(int sock) { }
void gui_real_conn_list_dialog_update(void) { }
void gui_close_connection_dialog(void) { }
void gui_add_idle_callback(void (*callback)(void *), void *data) { }
void gui_sound_bell(void) { }

/* Client page functions */
void gui_real_set_client_page(int page) { }
int gui_get_current_client_page(void) { return 0; }

/* Unit/focus functions */
void gui_set_unit_icon(int idx, struct unit *punit) { }
void gui_set_unit_icons_more_arrow(bool onoff) { }
void gui_real_focus_units_changed(void) { }
void gui_gui_update_font(const char *font_name) { }

/* Editor GUI functions */
void gui_editgui_refresh(void) { }
void gui_editgui_notify_object_created(void *object, int object_id) { }
void gui_editgui_notify_object_changed(int objtype, void *object, bool remove) { }
void gui_editgui_popup_properties(void *object, int objtype) { }
void gui_editgui_tileset_changed(void) { }
void gui_editgui_popdown_all(void) { }

/* Dialog functions */
void gui_popup_combat_info(void) { }
void gui_update_timeout_label(void) { }
void gui_start_turn(void) { }
void gui_real_city_dialog_popup(void *pdialog, int canvas_x, int canvas_y) { }
void gui_real_city_dialog_refresh(void *pdialog) { }
void gui_popdown_city_dialog(void *pdialog) { }
void gui_popdown_all_city_dialogs(void) { }
void gui_handmade_scenario_warning(void) { }
void gui_refresh_unit_city_dialogs(void *unit) { }
bool gui_city_dialog_is_open(void *pcity) { return false; }

/* Request transport */
void gui_request_transport(void *unit, void *dest_tile) { }

/* Infra dialog */
void gui_update_infra_dialog(void) { }

/* Theme functions */
void gui_gui_load_theme(const char *theme_name) { }
void gui_gui_clear_theme(void) { }
void *gui_get_gui_specific_themes_directories(void) { return NULL; }
void *gui_get_usable_themes_in_directory(const char *dirname) { return NULL; }

/* Image popup */
void gui_popup_image(const char *tag) { }

/* GUI properties setup */
void gui_setup_gui_properties(void) {
  gui_properties.views.isometric = TRUE;
}
