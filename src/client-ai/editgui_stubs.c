/* GUI callback stubs for headless client */

#ifdef HAVE_CONFIG_H
#include <fc_config.h>
#endif

#include <stdbool.h>
#include <stddef.h>

/* common */
#include "fc_types.h"

/* client */
#include "gui_stub.h"

/* Enums and types */
enum gui_type gui_get_gui_type(void) { return GUI_STUB; }
void gui_insert_client_build_info(char *outbuf, size_t outlen) { }

/* Options */
void gui_options_extra_init(void) { }

/* Network */
void gui_add_net_input(int sock) { }
void gui_remove_net_input(int sock) { }
void gui_real_conn_list_dialog_update(void) { }

/* Callbacks */
void gui_add_idle_callback(void (*callback)(void *), void *data) { }
void gui_sound_bell(void) { }

/* Unit functions */
void gui_set_unit_icon(int idx, struct unit *punit) { }
void gui_set_unit_icons_more_arrow(bool onoff) { }
void gui_real_focus_units_changed(void) { }

/* Font update */
void gui_gui_update_font(const char *font_name) { }

/* Editor GUI functions */
void gui_editgui_refresh(void) { }
void gui_editgui_notify_object_created(void *object, int object_id) { }
void gui_editgui_notify_object_changed(int objtype, void *object, bool remove) { }
void gui_editgui_popup_properties(void *object, int objtype) { }
void gui_editgui_tileset_changed(void) { }
void gui_editgui_popdown_all(void) { }

/* GUI properties setup */
void gui_setup_gui_properties(void) { }
