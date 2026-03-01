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

/* common */
#include "game.h"
#include "government.h"
#include "actions.h"
#include "actres.h"
#include "tile.h"
#include "map.h"
#include "unittype.h"

/* utility */
#include "log.h"

/* client */
#include "control.h"

/* internal action-decision API shared with freeciv_ai.c */
#include "../freeciv-ai-lib/freeciv_ai_action.h"

/* gui main header */
#include "gui_stub.h"

#include "dialogs.h"

/**********************************************************************//**
  Popup a dialog to display information about an event that has a
  specific location.  The user should be given the option to goto that
  location.
**************************************************************************/
void popup_notify_goto_dialog(const char *headline, const char *lines,
                              const struct text_tag_list *tags,
                              struct tile *ptile)
{
  /* PORTME */
}

/**********************************************************************//**
  Popup a dialog to display connection message from server.
**************************************************************************/
void popup_connect_msg(const char *headline, const char *message)
{
  /* PORTME */
}

/**********************************************************************//**
  Popup a generic dialog to display some generic information.
**************************************************************************/
void popup_notify_dialog(const char *caption, const char *headline,
			 const char *lines)
{
  /* PORTME */
}

/**********************************************************************//**
  Popup the nation selection dialog.
**************************************************************************/
void popup_races_dialog(struct player *pplayer)
{
  /* PORTME */
}

/**********************************************************************//**
  Close the nation selection dialog.  This should allow the user to
  (at least) select a unit to activate.
**************************************************************************/
void popdown_races_dialog(void)
{
  /* PORTME */
}

/**********************************************************************//**
  Popup a dialog window to select units on a particular tile.
**************************************************************************/
void unit_select_dialog_popup(struct tile *ptile)
{
  /* PORTME */
}

/**********************************************************************//**
  Update the dialog window to select units on a particular tile.
**************************************************************************/
void unit_select_dialog_update_real(void *unused)
{
  /* PORTME */
}

/**********************************************************************//**
  The server has changed the set of selectable nations.
**************************************************************************/
void races_update_pickable(bool nationset_change)
{
  /* PORTME */
}

/**********************************************************************//**
  In the nation selection dialog, make already-taken nations unavailable.
  This information is contained in the packet_nations_used packet.
**************************************************************************/
void races_toggles_set_sensitive(void)
{
  /* PORTME */
}

/**********************************************************************//**
  Popup a dialog asking if the player wants to start a revolution.
**************************************************************************/
void popup_revolution_dialog(void)
{
  /* PORTME */
}

/**********************************************************************//**
  Popup a dialog that allows the player to select what action a unit
  should take.
**************************************************************************/
void popup_action_selection(struct unit *actor_unit,
                            struct city *target_city,
                            struct unit *target_unit,
                            struct tile *target_tile,
                            struct extra_type *target_extra,
                            const struct act_prob *act_probs)
{
  int actor_id = actor_unit ? actor_unit->id : IDENTITY_NUMBER_ZERO;
  freeciv_action_decision_t dec;

  dec.actor_id  = actor_id;
  dec.n_choices = 0;

  if (actor_unit && act_probs) {
    action_iterate(act_id) {
      if (!action_prob_possible(act_probs[act_id])) {
        continue;
      }
      if (dec.n_choices >= 64) {
        break;
      }

      freeciv_action_choice_t *c = &dec.choices[dec.n_choices++];
      c->action_id = act_id;
      strncpy(c->name,
              action_name_translation(action_by_number(act_id)),
              sizeof(c->name) - 1);
      c->name[sizeof(c->name) - 1] = '\0';
      c->min_prob = act_probs[act_id].min;

      /* Pre-resolve target_id for this action's target kind. */
      switch (action_get_target_kind(action_by_number(act_id))) {
      case ATK_SELF:
        c->target_id = IDENTITY_NUMBER_ZERO;
        break;
      case ATK_TILE:
      case ATK_EXTRAS:
      case ATK_STACK:
        c->target_id = target_tile
          ? tile_index(target_tile) : IDENTITY_NUMBER_ZERO;
        break;
      case ATK_UNIT:
        c->target_id = target_unit
          ? target_unit->id : IDENTITY_NUMBER_ZERO;
        break;
      case ATK_CITY:
        c->target_id = target_city
          ? target_city->id : IDENTITY_NUMBER_ZERO;
        break;
      default:
        c->target_id = IDENTITY_NUMBER_ZERO;
        break;
      }
    } action_iterate_end;
  }

  /* Push the decision for the Python REPL to read, then unblock the
   * client event loop.  action_decision_clear_want() is called later by
   * freeciv_ai_resolve_action_decision() or
   * freeciv_ai_cancel_action_decision() once the player has chosen. */
  freeciv_ai_push_action_decision(&dec);
  action_selection_no_longer_in_progress(actor_id);
}

/**********************************************************************//**
  Popup a window asking a diplomatic unit if it wishes to incite the
  given enemy city.
**************************************************************************/
void popup_incite_dialog(struct unit *actor, struct city *pcity, int cost,
                         const struct action *paction)
{
  /* PORTME */
}

/**********************************************************************//**
  Popup a dialog asking a diplomatic unit if it wishes to bribe the
  given enemy unit.
**************************************************************************/
void popup_bribe_unit_dialog(struct unit *actor, struct unit *punit, int cost,
                             const struct action *paction)
{
  /* PORTME */
}

/**********************************************************************//**
  Popup a dialog asking a diplomatic unit if it wishes to bribe the
  given enemy unit stack.
**************************************************************************/
void popup_bribe_stack_dialog(struct unit *actor, struct tile *ptile, int cost,
                              const struct action *paction)
{
  /* PORTME */
}

/**********************************************************************//**
  Popup a dialog asking a diplomatic unit if it wishes to sabotage the
  given enemy city.
**************************************************************************/
void popup_sabotage_dialog(struct unit *actor, struct city *pcity,
                           const struct action *paction)
{
  /* PORTME */
}

/***********************************************************************//**
  Popup dialog for upgrade units
***************************************************************************/
void popup_upgrade_dialog(struct unit_list *punits)
{
  /* PORTME */
}

/**********************************************************************//**
  Popup a dialog asking the unit which improvement they would like to
  pillage.
**************************************************************************/
void popup_pillage_dialog(struct unit *punit, bv_extras may_pillage)
{
  /* PORTME */
}

/**********************************************************************//**
  Pops up a dialog to confirm disband of the unit(s).
**************************************************************************/
void popup_disband_dialog(struct unit_list *punits)
{
  /* PORTME */
}

/**********************************************************************//**
  Ruleset (modpack) has suggested loading certain tileset. Confirm from
  user and load.
**************************************************************************/
void popup_tileset_suggestion_dialog(void)
{
  /* PORTME */
}

/**********************************************************************//**
  Ruleset (modpack) has suggested loading certain soundset. Confirm from
  user and load.
**************************************************************************/
void popup_soundset_suggestion_dialog(void)
{
  /* PORTME */
}

/**********************************************************************//**
  Ruleset (modpack) has suggested loading certain musicset. Confirm from
  user and load.
**************************************************************************/
void popup_musicset_suggestion_dialog(void)
{
  /* PORTME */
}

/**********************************************************************//**
  Tileset (modpack) has suggested loading certain theme. Confirm from
  user and load.
**************************************************************************/
bool popup_theme_suggestion_dialog(const char *theme_name)
{
  /* PORTME */
  return FALSE;
}

/**********************************************************************//**
  This function is called when the client disconnects or the game is
  over.  It should close all dialog windows for that game.
**************************************************************************/
void popdown_all_game_dialogs(void)
{
  /* PORTME */
}

/**********************************************************************//**
  Returns the id of the actor unit currently handled in action selection
  dialog when the action selection dialog is open.
  Returns IDENTITY_NUMBER_ZERO if no action selection dialog is open.
**************************************************************************/
int action_selection_actor_unit(void)
{
  /* PORTME */
  return IDENTITY_NUMBER_ZERO;
}

/**********************************************************************//**
  Returns id of the target city of the actions currently handled in action
  selection dialog when the action selection dialog is open and it has a
  city target. Returns IDENTITY_NUMBER_ZERO if no action selection dialog
  is open or no city target is present in the action selection dialog.
**************************************************************************/
int action_selection_target_city(void)
{
  /* PORTME */
  return IDENTITY_NUMBER_ZERO;
}

/**********************************************************************//**
  Returns id of the target unit of the actions currently handled in action
  selection dialog when the action selection dialog is open and it has a
  unit target. Returns IDENTITY_NUMBER_ZERO if no action selection dialog
  is open or no unit target is present in the action selection dialog.
**************************************************************************/
int action_selection_target_unit(void)
{
  return IDENTITY_NUMBER_ZERO;
}

/**********************************************************************//**
  Returns id of the target tile of the actions currently handled in action
  selection dialog when the action selection dialog is open and it has a
  tile target. Returns TILE_INDEX_NONE if no action selection dialog is
  open.
**************************************************************************/
int action_selection_target_tile(void)
{
  return TILE_INDEX_NONE;
}

/**********************************************************************//**
  Returns id of the target extra of the actions currently handled in action
  selection dialog when the action selection dialog is open and it has an
  extra target. Returns EXTRA_NONE if no action selection dialog is open
  or no extra target is present in the action selection dialog.
**************************************************************************/
int action_selection_target_extra(void)
{
  return EXTRA_NONE;
}

/**********************************************************************//**
  Updates the action selection dialog with new information.
**************************************************************************/
void action_selection_refresh(struct unit *actor_unit,
                              struct city *target_city,
                              struct unit *target_unit,
                              struct tile *target_tile,
                              struct extra_type *target_extra,
                              const struct act_prob *act_probs)
{
  /* TODO: port me. */
}

/**********************************************************************//**
  Closes the action selection dialog
**************************************************************************/
void action_selection_close(void)
{
  /* PORTME */
}

/**********************************************************************//**
  Let the non shared client code know that the action selection process
  no longer is in progress for the specified unit.

  This allows the client to clean up any client specific assumptions.
**************************************************************************/
void action_selection_no_longer_in_progress_gui_specific(int actor_id)
{
  /* PORTME */
}

/**********************************************************************//**
  Player has gained a new tech.
**************************************************************************/
void show_tech_gained_dialog(Tech_type_id tech)
{
  /* PORTME */
}

/**********************************************************************//**
  Show tileset error dialog.
**************************************************************************/
void show_tileset_error(bool fatal, const char *tset_name, const char *msg)
{
  /* PORTME */
}

/**********************************************************************//**
  Give a warning when user is about to edit scenario with manually
  set properties.
**************************************************************************/
bool gui_handmade_scenario_warning(void)
{
  /* Just tell the client common code to handle this. */
  return FALSE;
}

/**********************************************************************//**
  Unit wants to get into some transport on given tile.
**************************************************************************/
bool gui_request_transport(struct unit *pcargo, struct tile *ptile)
{
  return FALSE; /* Unit was not handled here. */
}

/**********************************************************************//**
  Popup detailed information about battle or save information for
  some kind of statistics
**************************************************************************/
void gui_popup_combat_info(int attacker_unit_id, int defender_unit_id,
                           int attacker_hp, int defender_hp,
                           bool make_att_veteran, bool make_def_veteran)
{
}

/**********************************************************************//**
  Common code wants confirmation for an action.
**************************************************************************/
void gui_request_action_confirmation(const char *expl,
                                     struct act_confirmation_data *data)
{
  /* Just confirm */
  action_confirmation(data, TRUE);
}

/**********************************************************************//**
  Popup image window
**************************************************************************/
void gui_popup_image(const char *tag)
{
}
