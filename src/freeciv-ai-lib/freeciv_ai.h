/*
 * Public API for libfreeciv_ai.
 *
 * C callers include this header directly and work with native freeciv types.
 * Python/CFFI callers use a simplified copy of these declarations in _lib.py
 * where enums become int and struct pointers become void *.
 */

#ifndef FREECIV_AI_H
#define FREECIV_AI_H

#ifdef __cplusplus
extern "C" {
#endif

/* utility */
#include "support.h"

/* common */
#include "unit.h"
#include "map_types.h"   /* enum direction8 */
#include "game.h"

/* client */
#include "client_main.h" /* enum client_states, can_client_issue_orders() */

/*
 * Plain-C snapshot of a unit, safe to copy across the library boundary.
 * Used by freeciv_ai_get_units() so that Python does not need the full
 * freeciv struct unit layout.
 */
typedef struct {
  int id;
  int x, y;
  int hp, hp_max;
  int moves_left, moves_max;
  char type_name[64];
} freeciv_unit_t;

/*
 * Plain-C snapshot of a map tile.
 * known: 0=TILE_UNKNOWN, 1=TILE_KNOWN_UNSEEN, 2=TILE_KNOWN_SEEN
 * index: tile index — pass as target_id to freeciv_ai_do_action() for
 *        tile-targeted actions (UNIT_MOVE, FOUND_CITY, FORTIFY, …).
 * owner: player index of owning player, -1 if none.
 * city_id: id of city on this tile, -1 if none.
 * n_units: number of units currently on this tile.
 * extras: bitmask of extra types present (first 32).
 */
typedef struct {
  int x, y;
  int index;
  int known;
  char terrain[32];
  int owner;
  int city_id;
  char city_name[64];
  int n_units;
  unsigned int extras;
} freeciv_tile_t;

/*
 * Plain-C snapshot of a city.
 * owner: player index.
 * size: city size (population class).
 * food_surplus / prod_surplus / trade / science: per-turn surpluses.
 * food_stock / granary_size: food storage towards next growth.
 * shield_stock / prod_cost: production progress / total cost.
 * prod_name: name of current production target.
 */
typedef struct {
  int id;
  char name[64];
  int x, y;
  int owner;
  int size;
  int food_surplus;
  int prod_surplus;
  int trade;
  int science;
  int food_stock;
  int granary_size;
  int shield_stock;
  int prod_cost;
  char prod_name[64];
} freeciv_city_t;

/*
 * Initialize the library.  Must be called before freeciv_ai_connect().
 * data_path: path to the freeciv/data directory, or NULL to rely on the
 *            FREECIV_DATA_PATH environment variable.
 */
void freeciv_ai_init(const char *data_path);

/*
 * Connect to a freeciv server synchronously.  Runs freeciv's client_main()
 * in a coroutine until the connection is established (or fails).
 * Returns 0 on success, -1 on failure.
 */
int freeciv_ai_connect(const char *host, int port, const char *username);

/* Returns the current freeciv client state. */
enum client_states freeciv_ai_get_client_state(void);

/*
 * Returns the raw socket file descriptor for the active server connection,
 * or -1 when not connected.  Python passes this to select() and calls
 * freeciv_ai_input() when data is available.
 */
int freeciv_ai_get_socket(void);

/*
 * Process one round of incoming packets on fd.  Call after select() reports
 * the socket is readable.  Also updates the cached client state.
 */
void freeciv_ai_input(int fd);

/* Returns TRUE if the local player can issue orders this turn. */
bool freeciv_ai_can_act(void);

/* Send a "turn done" packet to the server. */
void freeciv_ai_end_turn(void);

/* Returns the current game turn number. */
int freeciv_ai_get_turn(void);

/*
 * Fill buf with up to max_units snapshot entries for the local player.
 * Returns the number of entries written.
 */
int freeciv_ai_get_units(freeciv_unit_t *buf, int max_units);

/* Look up a unit by its ID.  Returns NULL when not found. */
struct unit *freeciv_ai_get_unit(int unit_id);

/*
 * Request that unit_id move one step in direction dir.
 * Uses freeciv's enum direction8 (DIR8_NORTH, DIR8_NORTHEAST, …).
 */
void freeciv_ai_move_unit(int unit_id, enum direction8 dir);

/*
 * Send a chat message or server command to the server.
 * Messages starting with '/' are treated as server commands
 * (e.g. "/set timeout 30", "/start", "/quit").
 * Command access requires sufficient server access level.
 * Returns the number of bytes sent, or -1 on error.
 */
int freeciv_ai_send_chat(const char *message);

/*
 * Returns TRUE if this client has been granted 'hack' access level by
 * the server.  Hack level is negotiated automatically on localhost via a
 * filesystem challenge, so it is available when the server runs as the same
 * user on the same machine.  For remote servers the admin must grant it with
 * /cmdlevel hack <username> from the server console.
 */
bool freeciv_ai_has_hack(void);

/* Disconnect from the server and clean up. */
void freeciv_ai_stop(void);

/* ------------------------------------------------------------------ */
/* Map                                                                  */
/* ------------------------------------------------------------------ */

/* Map dimensions. */
int freeciv_ai_map_width(void);
int freeciv_ai_map_height(void);

/* Map topology: bitmask of topo_flag (TF_ISO=1, TF_HEX=2). */
int freeciv_ai_map_topology_id(void);
/* Map wrapping: bitmask of wrap_flag (WRAP_X=1, WRAP_Y=2). */
int freeciv_ai_map_wrap_id(void);

/*
 * Convert (x, y) to a tile index suitable as target_id in
 * freeciv_ai_do_action() and freeciv_ai_can_do_action().
 * Returns -1 for invalid coordinates.
 */
int freeciv_ai_tile_index(int x, int y);

/*
 * Fill buf with up to max_tiles tile snapshots for all tiles.
 * Returns the number of entries written.
 */
int freeciv_ai_get_tiles(freeciv_tile_t *buf, int max_tiles);

/*
 * Fill buf with up to max_units unit snapshots for every unit on
 * tile (x, y).  Returns the number of entries written.
 */
int freeciv_ai_get_tile_units(int x, int y,
                               freeciv_unit_t *buf, int max_units);

/* ------------------------------------------------------------------ */
/* Cities                                                               */
/* ------------------------------------------------------------------ */

/*
 * Fill buf with up to max_cities city snapshots for the local player.
 * Returns the number of entries written.
 */
int freeciv_ai_get_cities(freeciv_city_t *buf, int max_cities);

/* ------------------------------------------------------------------ */
/* Interactive action selection                                          */
/* ------------------------------------------------------------------ */

/* Structs and freeciv_ai_push_action_decision() are in the internal
 * header so that dialogs.c (in src/client-ai/) can include it without
 * pulling in all of freeciv_ai.h's Freeciv dependencies. */
#include "freeciv_ai_action.h"

/*
 * Returns 1 if an action decision is waiting for player input, else 0.
 * Copies the pending decision into *out.
 */
int freeciv_ai_get_action_decision(freeciv_action_decision_t *out);

/*
 * Execute action_id from the pending decision and clear the pending flag.
 * target_id must match the choice's pre-resolved target_id.
 */
void freeciv_ai_resolve_action_decision(int actor_id, int action_id,
                                        int target_id);

/*
 * Cancel the pending action decision (no action taken).
 * Tells the server not to queue any action for actor_id.
 */
void freeciv_ai_cancel_action_decision(int actor_id);

/* ------------------------------------------------------------------ */
/* Unit actions                                                          */
/* ------------------------------------------------------------------ */

/*
 * Check whether unit_id can perform action_id against target_id.
 *
 * The meaning of target_id depends on the action's target kind:
 *   ATK_SELF  — target_id is ignored
 *   ATK_TILE / ATK_EXTRAS / ATK_STACK — target_id is a tile index
 *     (obtain with freeciv_ai_tile_index(x,y))
 *   ATK_UNIT  — target_id is a unit id
 *   ATK_CITY  — target_id is a city id
 *
 * Returns the minimum action-success probability (0–200, where 200 =
 * certain), or -1 when the action is impossible / invalid.
 */
int freeciv_ai_can_do_action(int unit_id, int action_id, int target_id);

/*
 * Ask the server to perform action_id with actor unit_id against target_id.
 *
 * sub_tgt: sub-target (tech id, building id, etc.) — 0 for most actions.
 * name:    city/unit name for actions that require one (e.g. FOUND_CITY);
 *          pass NULL or "" otherwise.
 *
 * The target_id semantics are the same as for freeciv_ai_can_do_action().
 */
void freeciv_ai_do_action(int unit_id, int action_id, int target_id,
                           int sub_tgt, const char *name);

#ifdef __cplusplus
}
#endif

#endif /* FREECIV_AI_H */
