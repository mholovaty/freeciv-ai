/*
 * freeciv_ai.c — shared-library entry point and public API.
 *
 * Architecture (single-threaded, POSIX coroutine via ucontext):
 *
 *   freeciv_ai_connect() sets up a coroutine that runs client_main().
 *   client_main() calls gui_ui_main() which connects to the server and
 *   then yields control back to Python via swapcontext.  Python owns the
 *   event loop: it calls select() and freeciv_ai_input() to process
 *   packets.  freeciv_ai_stop() resumes the coroutine so it can
 *   disconnect cleanly before client_exit() yields back to Python.
 */

#ifdef HAVE_CONFIG_H
#include <fc_config.h>
#endif

#define GUI_CB_MODE 1

#include <ucontext.h>
#include <setjmp.h>
#include <errno.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* utility */
#include "fc_cmdline.h"
#include "fciconv.h"
#include "log.h"
#include "support.h"

/* common */
#include "events.h"
#include "game.h"
#include "idex.h"
#include "map.h"
#include "unit.h"
#include "unitlist.h"
#include "unittype.h"
#include "player.h"
#include "actions.h"
#include "actres.h"
#include "city.h"
#include "extras.h"
#include "tile.h"
#include "terrain.h"

/* client */
#include "client_main.h"
#include "clinet.h"
#include "chatline_common.h"
#include "connectdlg_common.h"
#include "control.h"
#include "dialogs_g.h"
#include "diplodlg_g.h"
#include "editgui_g.h"
#include "gui_cbsetter.h"
#include "gui_interface.h"
#include "gui_properties.h"
#include "options.h"
#include "repodlgs_g.h"
#include "sprite_g.h"
#include "tilespec.h"

#include "freeciv_ai.h"

/* ---- Required link-time globals ---- */

const char *client_string = "freeciv-ai-lib";
const char * const gui_character_encoding = "UTF-8";
const bool gui_use_transliteration = FALSE;

/* ---- Coroutine state ---- */

#define CORO_STACK_SIZE (8 * 1024 * 1024)

typedef enum {
  CORO_CONNECTED    = 1, /* gui_ui_main connected; Python drives the loop  */
  CORO_DISCONNECTED = 2, /* connection failed or client_exit() was called   */
} coro_status_t;

static ucontext_t     g_main_ctx;           /* Python / caller context      */
static ucontext_t     g_coro_ctx;           /* freeciv client_main context  */
static char          *g_coro_stack = NULL;  /* heap-allocated coroutine stack */
static coro_status_t  g_coro_status = CORO_DISCONNECTED;
static bool           g_in_coro = false;    /* true while coroutine is running */

/*
 * Yield from the coroutine back to the Python caller.
 * May only be called from inside the coroutine (g_in_coro == true).
 */
static void coro_yield(coro_status_t status)
{
  g_coro_status = status;
  g_in_coro = false;
  swapcontext(&g_coro_ctx, &g_main_ctx);
  /* Resumed by Python calling freeciv_ai_stop(). */
  g_in_coro = true;
}

/* ---- Internal state ---- */

static enum client_states g_last_state = C_S_INITIAL;
static int g_net_socket = -1;

/* Coroutine argv storage */
static int   g_coro_argc;
static char *g_coro_argv[16];
static char  g_argv_prog[]        = "freeciv-ai";
static char  g_argv_server_flag[] = "--server";
static char  g_argv_port_flag[]   = "--port";
static char  g_argv_name_flag[]   = "--name";
static char  g_argv_host[512];
static char  g_argv_port[32];
static char  g_argv_user[512];

static void ai_log_callback(enum log_level level, const char *message,
                             bool file_too)
{
  if (file_too) {
    return;
  }
  fprintf(stderr, "%d: %s\n", level, message);
}

/* Coroutine entry point: runs client_main() which eventually calls
 * gui_ui_main(), which yields back to Python. */
static void coro_entry(void)
{
  client_main(g_coro_argc, g_coro_argv, FALSE /* load tileset so handlers have a valid tileset* */);
  /* __wrap_client_exit should have yielded us back already; if we somehow
   * reach here, yield once more as a safety net. */
  coro_yield(CORO_DISCONNECTED);
}

/*
 * Intercept client_exit() via --wrap=client_exit so it does not call
 * exit() and kill the Python interpreter.
 */
void fc__noreturn __wrap_client_exit(int return_value)
{
  (void)return_value;
  /* client_exit() calls exit() at the end; that call is intercepted by
   * __wrap_exit() below (since client_exit and its exit() call are in the
   * same TU, --wrap=client_exit alone won't catch it). */
  g_last_state = C_S_DISCONNECTED;
  if (g_in_coro) {
    coro_yield(CORO_DISCONNECTED);
  }
  /* Should not reach here; spin as a safe fallback. */
  for (;;) {}
}

/*
 * Intercept exit() so that client_exit()'s final exit() call does not kill
 * the Python interpreter when we are inside the coroutine.
 */
void __wrap_exit(int status)
{
  if (g_in_coro) {
    g_last_state = C_S_DISCONNECTED;
    coro_yield(CORO_DISCONNECTED);
    for (;;) {}
  }
  /* Not in a coroutine — honour the real exit(). */
  extern void __real_exit(int status) __attribute__((noreturn));
  __real_exit(status);
}

/* ---- gui_* callbacks required by the freeciv client framework ---- */

void gui_ui_init(void) {}

void gui_ui_tileset_type_set(enum ts_type type)
{
  log_normal("STUB: tileset_type_set(%d)", type);
}

void gui_ui_exit(void) {}

void gui_options_extra_init(void) {}

void gui_real_conn_list_dialog_update(void *unused) {}

void gui_add_net_input(int sock)
{
  g_net_socket = sock;
}

void gui_remove_net_input(void)
{
  g_net_socket = -1;
}

/*
 * gui_ui_main() is called by client_main() after all freeciv subsystems
 * are initialised.  We connect to the server and, if successful, yield
 * back to Python.  Python drives the packet loop via freeciv_ai_input().
 * When freeciv_ai_stop() resumes us, we disconnect and return.
 */
int gui_ui_main(int argc, char *argv[])
{
  log_set_callback(ai_log_callback);

  /* Force every event type to also go to the output window (chatline) so
   * server command replies and other messages are captured by our log
   * callback.  By default most events are MW_MESSAGES-only, which routes
   * them to the silent meswin_add() stub. */
  for (int i = 0; i < E_COUNT; i++) {
    messages_where[i] |= MW_OUTPUT;
  }

  /* Allocate and zero-init the tileset struct so that packet handlers that
   * call tileset_ruleset_reset() have a valid object.  We never load actual
   * graphics, so this stays a lightweight empty shell. */
  tileset_init(tileset);

  /* Use ORDER_MOVE (not ORDER_ACTION_MOVE) for every directional move so
   * the server never sends a PACKET_UNIT_ACTIONS asking for per-move
   * confirmation.  The action-selection dialog flow is only needed for
   * deliberate actions; simple movement should just move. */
  gui_options.popup_last_move_to_allied = FALSE;

  /* Never ask about "passive" arrival actions (unit walks onto a tile
   * without explicitly targeting anything). */
  gui_options.popup_actor_arrival = FALSE;

  char errbuf[512];

  if (connect_to_server(user_name, server_host, server_port,
                        errbuf, sizeof(errbuf)) != -1) {
    g_last_state = C_S_PREPARING;
    coro_yield(CORO_CONNECTED);   /* Give control to Python. */
    /* Resumed here by freeciv_ai_stop(). */
    disconnect_from_server(false);
  } else {
    fprintf(stderr, "freeciv_ai: connection failed: %s\n", errbuf);
    g_last_state = C_S_DISCONNECTED;
  }

  start_quitting();
  return EXIT_SUCCESS;
}

/* ---- Public API ---- */

void freeciv_ai_init(const char *data_path)
{
  if (data_path) {
    setenv("FREECIV_DATA_PATH", data_path, 1);
  }

  setup_gui_funcs();

  struct gui_funcs *f = get_gui_funcs();
  f->tileset_type_set                  = gui_ui_tileset_type_set;
  f->load_gfxnumber                    = gui_load_gfxnumber;
  f->canvas_put_sprite_full_scaled     = gui_canvas_put_sprite_full_scaled;
  f->gui_init_meeting                  = gui_gui_init_meeting;
  f->gui_recv_cancel_meeting           = gui_gui_recv_cancel_meeting;
  f->gui_prepare_clause_updt           = gui_gui_prepare_clause_updt;
  f->gui_recv_create_clause            = gui_recv_create_clause;
  f->gui_recv_remove_clause            = gui_recv_remove_clause;
  f->gui_recv_accept_treaty            = gui_recv_accept_treaty;
  f->request_action_confirmation       = gui_request_action_confirmation;
  f->real_science_report_dialog_update = gui_real_science_report_dialog_update;
  f->science_report_dialog_redraw      = gui_science_report_dialog_redraw;
  f->science_report_dialog_popup       = gui_science_report_dialog_popup;
  f->real_economy_report_dialog_update = gui_real_economy_report_dialog_update;
  f->real_units_report_dialog_update   = gui_real_units_report_dialog_update;
  f->endgame_report_dialog_start       = gui_endgame_report_dialog_start;
  f->endgame_report_dialog_player      = gui_endgame_report_dialog_player;
}

/*
 * Connect to a freeciv server.  Runs client_main() in a coroutine until
 * the connection is established (or fails).  Returns 0 on success, -1 on
 * failure.
 */
int freeciv_ai_connect(const char *host, int port, const char *username)
{
  snprintf(g_argv_host, sizeof(g_argv_host), "%s", host);
  snprintf(g_argv_port, sizeof(g_argv_port), "%d", port);
  snprintf(g_argv_user, sizeof(g_argv_user), "%s", username);

  g_coro_argv[0] = g_argv_prog;
  g_coro_argv[1] = g_argv_server_flag;
  g_coro_argv[2] = g_argv_host;
  g_coro_argv[3] = g_argv_port_flag;
  g_coro_argv[4] = g_argv_port;
  g_coro_argv[5] = g_argv_name_flag;
  g_coro_argv[6] = g_argv_user;
  g_coro_argv[7] = NULL;
  g_coro_argc = 7;

  g_last_state = C_S_INITIAL;

  /* Allocate coroutine stack. */
  g_coro_stack = fc_malloc(CORO_STACK_SIZE);

  /* Set up coroutine context. */
  getcontext(&g_coro_ctx);
  g_coro_ctx.uc_stack.ss_sp   = g_coro_stack;
  g_coro_ctx.uc_stack.ss_size = CORO_STACK_SIZE;
  g_coro_ctx.uc_link          = NULL;
  makecontext(&g_coro_ctx, coro_entry, 0);

  /* Switch into the coroutine; it runs until connect (or fails). */
  g_in_coro = true;
  swapcontext(&g_main_ctx, &g_coro_ctx);
  /* We're back: coroutine yielded. */

  if (g_coro_status == CORO_CONNECTED) {
    return 0;
  }

  /* Connection failed; coroutine has already exited. */
  free(g_coro_stack);
  g_coro_stack = NULL;
  return -1;
}

enum client_states freeciv_ai_get_client_state(void)
{
  return g_last_state;
}

/*
 * Returns the raw socket fd for the server connection, or -1 when not
 * connected.  Python passes this to select() and calls freeciv_ai_input()
 * when data is available.
 */
int freeciv_ai_get_socket(void)
{
  return g_net_socket;
}

/*
 * Process incoming server data.  Call after select() says fd is readable.
 * Updates the cached client state so Python can observe transitions.
 */
void freeciv_ai_input(int fd)
{
  input_from_server(fd);

  enum client_states cs = client_state();
  if (cs != g_last_state) {
    g_last_state = cs;
  }
}

int freeciv_ai_send_chat(const char *message)
{
  return send_chat(message);
}

bool freeciv_ai_has_hack(void)
{
  return can_client_access_hack();
}

/*
 * Disconnect and clean up.  Resumes the coroutine so it can call
 * disconnect_from_server() before client_exit() yields back to us.
 */
void freeciv_ai_stop(void)
{
  if (!g_coro_stack) {
    return; /* Never connected, or already stopped. */
  }

  g_in_coro = true;
  swapcontext(&g_main_ctx, &g_coro_ctx);
  /* Coroutine has finished (client_exit was called → CORO_DISCONNECTED). */

  free(g_coro_stack);
  g_coro_stack = NULL;
}

bool freeciv_ai_can_act(void)
{
  return can_client_issue_orders();
}

void freeciv_ai_end_turn(void)
{
  send_turn_done();
}

int freeciv_ai_get_turn(void)
{
  return game.info.turn;
}

int freeciv_ai_get_units(freeciv_unit_t *buf, int max_units)
{
  struct player *pplayer = client_player();

  if (!pplayer || !buf || max_units <= 0) {
    return 0;
  }

  int count = 0;
  unit_list_iterate(pplayer->units, punit) {
    if (count >= max_units) {
      break;
    }
    freeciv_unit_t *u = &buf[count++];
    const struct unit_type *ut = unit_type_get(punit);
    u->id         = punit->id;
    u->x          = index_to_map_pos_x(tile_index(unit_tile(punit)));
    u->y          = index_to_map_pos_y(tile_index(unit_tile(punit)));
    u->hp         = punit->hp;
    u->hp_max     = ut->hp;
    u->moves_left = punit->moves_left;
    u->moves_max  = ut->move_rate;
    strncpy(u->type_name, utype_name_translation(ut), sizeof(u->type_name) - 1);
    u->type_name[sizeof(u->type_name) - 1] = '\0';
  } unit_list_iterate_end;

  return count;
}

struct unit *freeciv_ai_get_unit(int unit_id)
{
  return game_unit_by_number(unit_id);
}

void freeciv_ai_move_unit(int unit_id, enum direction8 dir)
{
  struct unit *punit = game_unit_by_number(unit_id);

  if (punit) {
    request_move_unit_direction(punit, dir);
  }
}

/* ------------------------------------------------------------------ */
/* Map                                                                  */
/* ------------------------------------------------------------------ */

int freeciv_ai_map_width(void)
{
  return wld.map.xsize;
}

int freeciv_ai_map_height(void)
{
  return wld.map.ysize;
}

int freeciv_ai_tile_index(int x, int y)
{
  struct tile *ptile = map_pos_to_tile(&wld.map, x, y);
  return ptile ? tile_index(ptile) : -1;
}

int freeciv_ai_get_tiles(freeciv_tile_t *buf, int max_tiles)
{
  struct player *pplayer = client_player();

  if (!buf || max_tiles <= 0) {
    return 0;
  }

  int count = 0;
  whole_map_iterate(&wld.map, ptile) {
    if (count >= max_tiles) {
      break;
    }
    freeciv_tile_t *t = &buf[count++];
    t->x     = index_to_map_pos_x(tile_index(ptile));
    t->y     = index_to_map_pos_y(tile_index(ptile));
    t->index = tile_index(ptile);

    enum known_type known = pplayer
      ? tile_get_known(ptile, pplayer)
      : TILE_UNKNOWN;
    t->known = (int)known;

    t->owner = ptile->owner ? player_index(ptile->owner) : -1;

    if (known == TILE_UNKNOWN) {
      t->terrain[0] = '\0';
      t->city_id    = -1;
      t->city_name[0] = '\0';
      t->n_units    = 0;
      t->extras     = 0;
    } else {
      struct terrain *pterr = tile_terrain(ptile);
      if (pterr) {
        strncpy(t->terrain, terrain_rule_name(pterr),
                sizeof(t->terrain) - 1);
        t->terrain[sizeof(t->terrain) - 1] = '\0';
      } else {
        t->terrain[0] = '\0';
      }

      struct city *pcity = tile_city(ptile);
      if (pcity) {
        t->city_id = pcity->id;
        strncpy(t->city_name, city_name_get(pcity),
                sizeof(t->city_name) - 1);
        t->city_name[sizeof(t->city_name) - 1] = '\0';
      } else {
        t->city_id      = -1;
        t->city_name[0] = '\0';
      }

      t->n_units = unit_list_size(ptile->units);

      unsigned int extras_mask = 0;
      extra_type_iterate(pextra) {
        int idx = extra_index(pextra);
        if (idx < 32 && tile_has_extra(ptile, pextra)) {
          extras_mask |= (1u << idx);
        }
      } extra_type_iterate_end;
      t->extras = extras_mask;
    }
  } whole_map_iterate_end;

  return count;
}

int freeciv_ai_get_tile_units(int x, int y,
                               freeciv_unit_t *buf, int max_units)
{
  struct tile *ptile = map_pos_to_tile(&wld.map, x, y);
  if (!ptile || !buf || max_units <= 0) {
    return 0;
  }

  int count = 0;
  unit_list_iterate(ptile->units, punit) {
    if (count >= max_units) {
      break;
    }
    freeciv_unit_t *u = &buf[count++];
    const struct unit_type *ut = unit_type_get(punit);
    u->id         = punit->id;
    u->x          = x;
    u->y          = y;
    u->hp         = punit->hp;
    u->hp_max     = ut->hp;
    u->moves_left = punit->moves_left;
    u->moves_max  = ut->move_rate;
    strncpy(u->type_name, utype_name_translation(ut),
            sizeof(u->type_name) - 1);
    u->type_name[sizeof(u->type_name) - 1] = '\0';
  } unit_list_iterate_end;

  return count;
}

/* ------------------------------------------------------------------ */
/* Cities                                                               */
/* ------------------------------------------------------------------ */

int freeciv_ai_get_cities(freeciv_city_t *buf, int max_cities)
{
  struct player *pplayer = client_player();

  if (!pplayer || !buf || max_cities <= 0) {
    return 0;
  }

  int count = 0;
  city_list_iterate(pplayer->cities, pcity) {
    if (count >= max_cities) {
      break;
    }
    freeciv_city_t *c = &buf[count++];
    c->id = pcity->id;
    strncpy(c->name, city_name_get(pcity), sizeof(c->name) - 1);
    c->name[sizeof(c->name) - 1] = '\0';

    struct tile *ctile = city_tile(pcity);
    c->x = index_to_map_pos_x(tile_index(ctile));
    c->y = index_to_map_pos_y(tile_index(ctile));

    c->owner        = player_index(pcity->owner);
    c->size         = city_size_get(pcity);
    c->food_surplus = pcity->surplus[O_FOOD];
    c->prod_surplus = pcity->surplus[O_SHIELD];
    c->trade        = pcity->surplus[O_TRADE];
  } city_list_iterate_end;

  return count;
}

/* ------------------------------------------------------------------ */
/* Unit actions                                                          */
/* ------------------------------------------------------------------ */

int freeciv_ai_can_do_action(int unit_id, int action_id, int target_id)
{
  struct unit *punit = game_unit_by_number(unit_id);
  if (!punit) {
    return -1;
  }
  if (!gen_action_is_valid((enum gen_action)action_id)) {
    return -1;
  }

  struct act_prob prob = ACTPROB_IMPOSSIBLE;
  enum action_target_kind tgt_kind =
    action_get_target_kind(action_by_number(action_id));

  switch (tgt_kind) {
  case ATK_SELF:
    prob = action_prob_self(&wld.map, punit, action_id);
    break;
  case ATK_TILE:
  case ATK_EXTRAS: {
    struct tile *ptile = index_to_tile(&wld.map, target_id);
    if (ptile) {
      prob = action_prob_vs_tile(&wld.map, punit, action_id, ptile, NULL);
    }
    break;
  }
  case ATK_UNIT: {
    struct unit *ptgt = game_unit_by_number(target_id);
    if (ptgt) {
      prob = action_prob_vs_unit(&wld.map, punit, action_id, ptgt);
    }
    break;
  }
  case ATK_STACK: {
    struct tile *ptile = index_to_tile(&wld.map, target_id);
    if (ptile) {
      prob = action_prob_vs_stack(&wld.map, punit, action_id, ptile);
    }
    break;
  }
  case ATK_CITY: {
    struct city *pcity = game_city_by_number(target_id);
    if (pcity) {
      prob = action_prob_vs_city(&wld.map, punit, action_id, pcity);
    }
    break;
  }
  default:
    break;
  }

  if (!action_prob_possible(prob)) {
    return -1;
  }
  return prob.min;
}

void freeciv_ai_do_action(int unit_id, int action_id, int target_id,
                           int sub_tgt, const char *name)
{
  if (!gen_action_is_valid((enum gen_action)action_id)) {
    return;
  }
  request_do_action((enum gen_action)action_id, unit_id, target_id,
                    sub_tgt, name ? name : "");
}
