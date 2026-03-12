/***********************************************************************
 Freeciv - Copyright (C) 1996 - A Kjeldberg, L Gregersen, P Unold
   This program is free software; you can redistribute it and/or modify
   it under the terms of the GNU General Public License as published by
   the Free Software Foundation; either version 2, or (at your option)
   any later version.

   This program is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
   GNU General Public License for more details.
***********************************************************************/

#ifdef HAVE_CONFIG_H
#include <fc_config.h>
#endif

#include <stdlib.h>

/* gui main header */
#include "gui_stub.h"

/* client */
#include "control.h"    /* request_do_action */

/* common */
#include "actions.h"    /* ACTION_FOUND_CITY */
#include "map.h"        /* tile_index */
#include "unit.h"       /* unit_tile */

#include "mapctrl.h"

/**********************************************************************//**
  Auto-found the city immediately using the server-suggested name.
  In the stub GUI there is no dialog — we accept the suggestion as-is.
**************************************************************************/
void popup_newcity_dialog(struct unit *punit, const char *suggestname)
{
  if (punit == NULL) {
    return;
  }
  struct tile *ptile = unit_tile(punit);
  if (ptile == NULL) {
    return;
  }
  punit->client.asking_city_name = FALSE;
  request_do_action(ACTION_FOUND_CITY, punit->id,
                    tile_index(ptile), 0,
                    (suggestname && suggestname[0]) ? suggestname : "City");
}

/**********************************************************************//**
  A turn done button should be provided for the player.  This function
  is called to toggle it between active/inactive.
**************************************************************************/
void set_turn_done_button_state(bool state)
{
  /* PORTME */
}

/**********************************************************************//**
  Draw a goto or patrol line at the current mouse position.
**************************************************************************/
void create_line_at_mouse_pos(void)
{
  /* PORTME */
}

/**********************************************************************//**
 The Area Selection rectangle. Called by center_tile_mapcanvas() and
 when the mouse pointer moves.
**************************************************************************/
void update_rect_at_mouse_pos(void)
{
  /* PORTME */
}
