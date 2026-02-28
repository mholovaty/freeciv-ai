"""
CFFI bindings for libfreeciv_ai.so.

The declarations below are a simplified copy of freeciv_ai.h suitable for
CFFI's ABI mode: enums are expressed as int, struct unit * becomes void *,
and bool becomes int.  The binary layout is compatible with the real types.
"""

import os
import cffi

ffi = cffi.FFI()

ffi.cdef("""
/*
 * Snapshot of a single unit — matches the freeciv_unit_t layout in freeciv_ai.h.
 * Maps to: struct { int id; int x, y; int hp, hp_max; int moves_left, moves_max;
 *                   char type_name[64]; }
 */
typedef struct {
    int id;
    int x, y;
    int hp, hp_max;
    int moves_left, moves_max;
    char type_name[64];
} freeciv_unit_t;

/*
 * enum client_states values (from freeciv/client/client_main.h):
 *   C_S_INITIAL      = 0
 *   C_S_DISCONNECTED = 1
 *   C_S_PREPARING    = 2
 *   C_S_RUNNING      = 3
 */

void freeciv_ai_init(const char *data_path);

/* Connect synchronously; returns 0 on success, -1 on failure */
int  freeciv_ai_connect(const char *host, int port, const char *username);

/* Returns enum client_states as int */
int  freeciv_ai_get_client_state(void);

/* Returns the server socket fd, or -1 when not connected */
int  freeciv_ai_get_socket(void);

/* Process one round of packets after select() says the socket is readable */
void freeciv_ai_input(int fd);

/* Returns bool as int (0/1) */
int  freeciv_ai_can_act(void);

void freeciv_ai_end_turn(void);

int  freeciv_ai_get_turn(void);

int  freeciv_ai_get_units(freeciv_unit_t *buf, int max_units);

/* Returns struct unit * as void *; pass to freeciv_ai_move_unit etc. */
void *freeciv_ai_get_unit(int unit_id);

/* direction is enum direction8 as int: N=0 NE=1 E=2 SE=3 S=4 SW=5 W=6 NW=7 */
void freeciv_ai_move_unit(int unit_id, int direction);

/*
 * Send a chat message or server command (prefixed with '/') to the server.
 * Requires sufficient server access level for commands.
 * Returns bytes sent, or -1 on error.
 */
int  freeciv_ai_send_chat(const char *message);

/*
 * Returns 1 if this client holds 'hack' access level on the server.
 * Hack level is negotiated automatically on localhost (filesystem challenge).
 * On remote servers the admin must grant it via /cmdlevel hack <username>.
 */
int  freeciv_ai_has_hack(void);

void freeciv_ai_stop(void);
""")


def _find_so() -> str:
    """Search common locations for libfreeciv_ai.so."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        # Installed alongside the package
        os.path.join(here, "libfreeciv_ai.so"),
        # Build tree (python/ lives one level below the repo root)
        os.path.join(here, "..", "..", "builddir", "src", "freeciv-ai-lib",
                     "libfreeciv_ai.so"),
        # System-wide
        "libfreeciv_ai.so",
    ]
    for path in candidates:
        resolved = os.path.realpath(path)
        if os.path.exists(resolved):
            return resolved
    raise FileNotFoundError(
        "Could not find libfreeciv_ai.so. "
        "Build the project first with:\n"
        "  cd builddir && ninja"
    )


def find_data_path(so_path: str) -> str | None:
    """
    Derive the freeciv/data directory from the .so location.

    The .so lives at  <build>/src/freeciv-ai-lib/libfreeciv_ai.so
    and freeciv/data is at  <repo-root>/freeciv/data — three dirname()
    steps up from the .so, then into freeciv/data.
    """
    path = os.path.dirname(os.path.realpath(so_path))  # …/freeciv-ai-lib
    path = os.path.dirname(path)                        # …/src
    path = os.path.dirname(path)                        # …/builddir
    path = os.path.dirname(path)                        # repo root
    data = os.path.join(path, "freeciv", "data")
    return data if os.path.isdir(data) else None


from ._logging import _ensure_so_capture


def load_lib(so_path: str = None) -> tuple:
    """Load the CFFI library handle.  Returns (lib, resolved_so_path)."""
    _ensure_so_capture()   # must happen before dlopen so .so output is captured
    resolved = so_path or _find_so()
    return ffi.dlopen(resolved), resolved
