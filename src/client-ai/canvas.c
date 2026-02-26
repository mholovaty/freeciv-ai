#ifdef HAVE_CONFIG_H
#include <fc_config.h>
#endif

/* gui main header */
#include "gui_stub.h"

#include "canvas.h"

struct canvas *gui_canvas_create(int width, int height)
{
  return NULL;
}

void gui_canvas_free(struct canvas *store)
{
}

void gui_canvas_set_zoom(struct canvas *store, float zoom)
{
}

bool gui_has_zoom_support(void)
{
  return FALSE;
}

void gui_canvas_mapview_init(struct canvas *store)
{

}

void gui_canvas_copy(struct canvas *dest, struct canvas *src,
                     int src_x, int src_y, int dest_x, int dest_y, int width,
                     int height)
{

}

void gui_canvas_put_sprite(struct canvas *pcanvas,
                           int canvas_x, int canvas_y,
                           struct sprite *sprite,
                           int offset_x, int offset_y, int width, int height)
{

}

void gui_canvas_put_sprite_full(struct canvas *pcanvas,
                                int canvas_x, int canvas_y,
                                struct sprite *sprite)
{

}

void gui_canvas_put_sprite_full_scaled(struct canvas *pcanvas,
                                       int canvas_x, int canvas_y,
                                       int canvas_w, int canvas_h,
                                       struct sprite *sprite)
{

}

void gui_canvas_put_sprite_fogged(struct canvas *pcanvas,
                                  int canvas_x, int canvas_y,
                                  struct sprite *psprite,
                                  bool fog, int fog_x, int fog_y)
{

}

void gui_canvas_put_rectangle(struct canvas *pcanvas,
                              struct color *pcolor,
                              int canvas_x, int canvas_y, int width, int height)
{

}

void gui_canvas_fill_sprite_area(struct canvas *pcanvas,
                                 struct sprite *psprite, struct color *pcolor,
                                 int canvas_x, int canvas_y)
{

}

void gui_canvas_put_line(struct canvas *pcanvas, struct color *pcolor,
                         enum line_type ltype, int start_x, int start_y,
                         int dx, int dy)
{

}

void gui_canvas_put_curved_line(struct canvas *pcanvas, struct color *pcolor,
                                enum line_type ltype, int start_x, int start_y,
                                int dx, int dy)
{

}

void gui_canvas_put_text(struct canvas *pcanvas, int canvas_x, int canvas_y,
                         enum client_font font, struct color *pcolor,
                         const char *ptext)
{

}
