/* Minimal GUI callback stubs for headless client */

#ifdef HAVE_CONFIG_H
#include <fc_config.h>
#endif

/* Enable GUI callback interface to get gui_* function declarations */
/* #define GUI_CB_MODE 1 */


#include <stdlib.h>
#include <stddef.h>
#include <stdbool.h>

/* utility */
#include "support.h"

/* common */
#include "fc_types.h"
#include "unit.h"
#include "tile.h"

/* client */
#include "gui_stub.h"
#include "gui_properties.h"


enum gui_type gui_get_gui_type(void) { return GUI_STUB; }

void gui_insert_client_build_info(char *outbuf, size_t outlen) { }


void gui_add_idle_callback(void (*callback)(void *), void *data)
{
  /* No canvas/rendering in AI client — drop idle rendering callbacks. */
}

void gui_sound_bell(void)
{}

/* Unit/focus functions */
void gui_set_unit_icon(int idx, struct unit *punit)
{}

void gui_set_unit_icons_more_arrow(bool onoff)
{}

void gui_real_focus_units_changed(void)
{}

void gui_gui_update_font(const char *font_name, const char *font_value)
{}

/* Editor GUI functions */
void gui_setup_gui_properties(void) {
  gui_properties.views.isometric = TRUE;
  log_normal("Isometric: %d", gui_properties.views.isometric);
}

void gui_editgui_tileset_changed(void)
{}

void gui_editgui_refresh(void)
{}

void gui_editgui_popup_properties(const struct tile_list *tiles, int objtype)
{}

void gui_editgui_popdown_all(void)
{}

void gui_editgui_notify_object_changed(int objtype, int object_id, bool removal)
{}

void gui_editgui_notify_object_created(int tag, int id)
{}
