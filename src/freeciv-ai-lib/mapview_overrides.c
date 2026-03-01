#include "mapview_common.h"
#include "mapview_g.h"

/* Declared by the linker --wrap mechanism. */
void __real_move_unit_map_canvas(struct unit *punit,
                                 struct tile *ptile, int dx, int dy);

void __wrap_move_unit_map_canvas(struct unit *punit,
                                 struct tile *ptile, int dx, int dy)
{
  /* mapview.store is NULL in headless mode — skip animation. */
  if (mapview.store == NULL) {
    return;
  }
  __real_move_unit_map_canvas(punit, ptile, dx, dy);
}
