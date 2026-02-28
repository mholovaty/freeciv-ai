/*
 * chatline.c — chatline GUI callbacks for freeciv_ai library.
 *
 * Replaces freeciv/client/gui-stub/chatline.c so that incoming chat /
 * server-response messages are forwarded to the C logger (and therefore
 * appear in the Python [CLIENT] log stream) instead of being silently
 * dropped.
 */

#ifdef HAVE_CONFIG_H
#include <fc_config.h>
#endif

/* utility */
#include "log.h"

/* client */
#include "chatline_common.h"
#include "climisc.h"

#include "chatline.h"

/**********************************************************************//**
  Called for every chat / server-response message received from the server.
  Forward to the freeciv log so it surfaces in the Python [CLIENT] stream.
**************************************************************************/
void gui_real_output_window_append(const char *astring,
                                   const struct text_tag_list *tags,
                                   int conn_id)
{
  if (astring && *astring) {
    /* Prefix "S: " routes this line to the [SERVER] logger on the Python
     * side (see _logging.py _read_pipe).  Regular "N: msg" lines go to
     * [CLIENT].  Server command responses are semantically server output. */
    fprintf(stderr, "S: %s\n", astring);
    fflush(stderr);
  }
}

void log_output_window(void)
{
  write_chatline_content(NULL);
}

void clear_output_window(void)
{
}

void gui_version_message(const char *vertext)
{
  output_window_append(ftc_client, vertext);
}
