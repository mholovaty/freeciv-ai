/* Minimal GUI callback stubs for headless client */

#ifdef HAVE_CONFIG_H
#include <fc_config.h>
#endif

#include <stdlib.h>
#include <stddef.h>
#include <stdbool.h>

/* GUI Dialog Functions */
void real_city_dialog_refresh(void *pdialog) { }
void real_city_dialog_popup(void *pdialog, int canvas_x, int canvas_y) { }
void real_conn_list_dialog_update(void) { }
void real_science_report_dialog_update(void) { }
void real_economy_report_dialog_update(void) { }
void real_units_report_dialog_update(void) { }

/* Canvas Functions */
void map_canvas_size_refresh(void) { }
struct sprite *crop_sprite(struct sprite *original, int x, int y,
                           int width, int height,
                           struct sprite *mask, int mask_offset_x,
                           int mask_offset_y) { return NULL; }
void free_sprite(struct sprite *s) { }

/* Client Page Functions */
void real_set_client_page(int page) { }
int get_current_client_page(void) { return 0; }

/* Callback Functions */
void add_idle_callback(void (*callback)(void *), void *data) { }
bool has_zoom_support(void) { return false; }

/* GUI Property Functions */
void gui_setup_gui_properties(void) { }
void gui_editgui_tileset_changed(void) { }
void gui_editgui_popdown_all(void) { }

/* Audio Functions */
void audio_sdl_init(void) { }

/* Additional GUI stubs for client_common library */
void gui_nation_dialog_popup(void) { }
void gui_unit_select_dialog_popdown(void) { }
void gui_unit_select_dialog_update(void) { }
void gui_prepare_clause_updt(void *pplayer, void *pdialog) { }
void gui_recv_remove_clause(int player_id, int clause_id) { }
void color_alloc(int red, int green, int blue) { }
int color_brightness_score(int red, int green, int blue) { return 0; }
void real_luaconsole_append(const char *astring) { }
