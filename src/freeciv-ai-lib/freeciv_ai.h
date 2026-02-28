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

#ifdef __cplusplus
}
#endif

#endif /* FREECIV_AI_H */
