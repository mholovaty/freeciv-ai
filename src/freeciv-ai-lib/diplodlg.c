#ifdef HAVE_CONFIG_H
#include <fc_config.h>
#endif

/* gui main header */
#include "gui_stub.h"

#include "diplodlg.h"

/**********************************************************************//**
  Update a player's acceptance status of a treaty (traditionally shown
  with the thumbs-up/thumbs-down sprite).
**************************************************************************/
void gui_gui_recv_accept_treaty(struct treaty *ptreaty, struct player *they)
{
}

/**********************************************************************//**
  Handle the start of a diplomacy meeting - usually by popping up a
  diplomacy dialog.
**************************************************************************/
void gui_gui_init_meeting(struct treaty *ptreaty, struct player *they,
                          struct player *initiator)
{
}

/**********************************************************************//**
  Update the diplomacy dialog by adding a clause.
**************************************************************************/
void gui_gui_recv_create_clause(struct treaty *ptreaty, struct player *they)
{
}

/**********************************************************************//**
  Update the diplomacy dialog when the meeting is canceled (the dialog
  should be closed).
**************************************************************************/
void gui_gui_recv_cancel_meeting(struct treaty *ptreaty, struct player *they,
                                 struct player *initiator)
{
}

/**********************************************************************//**
  Update the diplomacy dialog by removing a clause.
**************************************************************************/
void gui_gui_recv_remove_clause(struct treaty *ptreaty, struct player *they)
{
}

/**********************************************************************//**
  Prepare to clause creation or removal.
**************************************************************************/
void gui_gui_prepare_clause_updt(struct treaty *ptreaty, struct player *they)
{
}

/**********************************************************************//**
  Close all open diplomacy dialogs.

  Called when the client disconnects from game.
**************************************************************************/
void close_all_diplomacy_dialogs(void)
{
}
