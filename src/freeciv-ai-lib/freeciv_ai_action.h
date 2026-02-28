/*
 * Internal types shared between freeciv_ai.c and dialogs.c.
 * Only standard C types — no Freeciv headers required.
 */

#ifndef FREECIV_AI_ACTION_H
#define FREECIV_AI_ACTION_H

/* One available action in a pending decision. */
typedef struct {
  int action_id;
  char name[64];
  int target_id;  /* pre-resolved for the action's target kind */
  int min_prob;   /* 0-200, 200 = certain */
} freeciv_action_choice_t;

/* Pending action decision sent from popup_action_selection to Python. */
typedef struct {
  int actor_id;
  int n_choices;
  freeciv_action_choice_t choices[64];
} freeciv_action_decision_t;

/* Called by dialogs.c to enqueue a decision. Defined in freeciv_ai.c. */
void freeciv_ai_push_action_decision(const freeciv_action_decision_t *dec);

#endif /* FREECIV_AI_ACTION_H */
