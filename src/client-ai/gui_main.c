#ifdef HAVE_CONFIG_H
#include <fc_config.h>
#endif

/* Enable GUI callback interface to get gui_* function declarations */
#define GUI_CB_MODE 1

#include <stdio.h>
#include <sys/select.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <libgen.h>
#include <unistd.h>
#include <readline/readline.h>
#include <readline/history.h>

/* utility */
#include "fc_cmdline.h"
#include "fciconv.h"
#include "log.h"
#include "support.h"

/* common */
#include "unitlist.h"
#include "unit.h"
#include "player.h"
#include "unittype.h"

/* client */
#include "client_main.h"
#include "clinet.h"
#include "dialogs_g.h"
#include "diplodlg_g.h"
#include "repodlgs_g.h"
#include "editgui_g.h"
#include "gui_cbsetter.h"
#include "gui_interface.h"
#include "gui_properties.h"
#include "options.h"
#include "sprite_g.h"
#include "tilespec.h"


#include "gui_main.h"

static int net_socket = -1;

const char *client_string = "client-ai";

const char * const gui_character_encoding = "UTF-8";
const bool gui_use_transliteration = FALSE;

static bool readline_active = false;
static bool quitting = false;
static bool needs_redisplay = false;

void gui_ui_init(void)
{

}

void gui_ui_tileset_type_set(enum ts_type type)
{
  log_normal("STUB: gui_ui_tileset_type_set(%d)", type);
}

static void set_data_path(void)
{
  if (getenv("FREECIV_DATA_PATH") == NULL) {
    char exec_dir[4096];
    char data_path[4096];

    if (realpath("/proc/self/exe", exec_dir) != NULL) {
      /* exec path: builddir/src/client-ai/freeciv-client-ai */
      /* data path: freeciv/data */
      char *dir = dirname(exec_dir);  /* builddir/src/client-ai */
      dir = dirname(dir);             /* builddir/src */
      dir = dirname(dir);             /* builddir */
      dir = dirname(dir);             /* (freeciv-ai root) */

      snprintf(data_path, sizeof(data_path), "%s/freeciv/data", dir);

      if (access(data_path, F_OK) == 0) {
        setenv("FREECIV_DATA_PATH", data_path, 1);
      }
    }
  }
}

static void print_units(void)
{
  struct player *pplayer = client_player();

  if (pplayer == NULL) {
    printf("No player connected\n");
    return;
  }

  printf("=== Units for %s ===\n", player_name(pplayer));

  int count = 0;
  unit_list_iterate(pplayer->units, punit) {
    const char *utype_name = utype_name_translation(unit_type_get(punit));
    printf("  [%d] %s - HP: %d/%d\n",
           punit->id,
           utype_name,
           punit->hp,
           unit_type_get(punit)->hp);
    count++;
  } unit_list_iterate_end;

  printf("Total units: %d\n\n", count);
}

static void end_turn_cmd(void)
{
  if (!can_client_issue_orders()) {
    printf("Cannot issue orders - server may be busy or not your turn\n\n");
    return;
  }

  send_turn_done();
  printf("Turn ended. Waiting for server...\n\n");
}

static void do_quit(void);

static void show_help(void)
{
  printf("\n=== CLI Commands ===\n");
  printf("  units  - List all your units\n");
  printf("  end    - End your turn\n");
  printf("  help   - Show this help message\n");
  printf("  quit   - Exit the game\n\n");
}

static void process_command(const char *cmd)
{
  if (cmd == NULL || cmd[0] == '\0') {
    return;
  }

  char *cmd_copy = fc_strdup(cmd);

  int len = strlen(cmd_copy);
  while (len > 0 && isspace((unsigned char)cmd_copy[len - 1])) {
    cmd_copy[--len] = '\0';
  }

  while (*cmd_copy && isspace((unsigned char)*cmd_copy)) {
    cmd_copy++;
  }

  if (strlen(cmd_copy) == 0) {
    free(cmd_copy);
    return;
  }

  if (strcmp(cmd_copy, "units") == 0) {
    print_units();
  } else if (strcmp(cmd_copy, "end") == 0) {
    end_turn_cmd();
  } else if (strcmp(cmd_copy, "help") == 0) {
    show_help();
  } else if (strcmp(cmd_copy, "quit") == 0) {
    do_quit();
  } else {
    printf("Unknown command: '%s'\n", cmd_copy);
    printf("Type 'help' for available commands\n\n");
  }

  free(cmd_copy);
}

static void cli_log_callback(enum log_level level, const char *message,
                              bool file_too)
{
  if (quitting || file_too) {
    /* If logging to a file, log_write already handled it. */
    return;
  }
  if (readline_active) {
    fprintf(stderr, "\r\033[K%d: %s\n", level, message);
    rl_on_new_line();
    needs_redisplay = true;
  } else {
    fprintf(stderr, "%d: %s\n", level, message);
  }
}

static void do_quit(void)
{
  quitting = true;
  readline_active = false;
  rl_callback_handler_remove();
  printf("\nDisconnecting...\n");
  disconnect_from_server(false);
  start_quitting();
}

static void readline_handler(char *line)
{
  if (line == NULL) {
    do_quit();
    return;
  }
  if (*line) {
    add_history(line);
  }
  process_command(line);
  free(line);
}


static void cli_main_loop(void)
{
  log_normal("CLI Main Loop Started");

  char errbuf[512];
  fd_set readfs;
  struct timeval tv;
  int max_fd;

  if (connect_to_server(
        user_name,
        server_host,
        server_port,
        errbuf,
        sizeof(errbuf)) != -1) {
    log_normal("Connected to server successfully");

    printf("Connected to server. Type 'help' for commands.\n");
    rl_callback_handler_install("> ", readline_handler);
    readline_active = true;

    while (net_socket >= 0) {
      FD_ZERO(&readfs);
      FD_SET(net_socket, &readfs);
      FD_SET(STDIN_FILENO, &readfs);

      max_fd = (net_socket > STDIN_FILENO) ? net_socket : STDIN_FILENO;

      /* 100ms timeout to allow for graceful shutdown and state checking */
      tv.tv_sec = 0;
      tv.tv_usec = 100000;

      int ret = select(max_fd + 1,
                       &readfs, NULL,
                       NULL, &tv);

      if (ret < 0) {
        log_error("select() error");
        break;
      }

      /* Process incoming packets if socket is readable */
      if (ret > 0 && FD_ISSET(net_socket, &readfs)) {
        int sock = net_socket;
        input_from_server(sock);
        if (net_socket < 0) {
          printf("\r\033[KServer disconnected.\n");
          break;
        }
      }

      /* Process user input if stdin is readable */
      if (ret > 0 && FD_ISSET(STDIN_FILENO, &readfs)) {
        rl_callback_read_char();
      }

      /* Redraw prompt only if log output cleared it */
      if (needs_redisplay) {
        rl_redisplay();
        needs_redisplay = false;
      }

    }

    readline_active = false;
    rl_callback_handler_remove();

  } else {
    fc_fprintf(stderr, _("Error connecting to server: %s\n"), errbuf);
  }

}

int main(int argc, char **argv)
{
  set_data_path();

  setup_gui_funcs();

  /* Set-up missing GUI functions */
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


  return client_main(argc, argv, FALSE);
}

static void print_usage(const char *argv0)
{
  fc_fprintf(stderr,
             _("This is the Freeciv AI client - a headless client for AI gameplay\n\n"));
  fc_fprintf(stderr, _("Report bugs at %s\n"), BUG_URL);
}

static bool parse_options(int argc, char **argv)
{
  int i = 1;

  while (i < argc) {
    if (is_option("--help", argv[i])) {
      print_usage(argv[0]);
      return FALSE;
    } else {
      fc_fprintf(stderr, _("Unrecognized option: \"%s\"\n"), argv[i]);
      exit(EXIT_FAILURE);
    }
    i++;
  }

  return TRUE;
}

int gui_ui_main(int argc, char *argv[])
{
  if (!parse_options(argc, argv)) {
    return EXIT_FAILURE;
  }

  log_set_callback(cli_log_callback);

  tileset_init(tileset);
  tileset_load_tiles(tileset);
  tileset_use_preferred_theme(tileset);

  cli_main_loop();

  start_quitting();

  tileset_free_tiles(tileset);

  return EXIT_SUCCESS;
}

void gui_ui_exit(void)
{

}

void gui_options_extra_init(void) {

}

void gui_add_net_input(int sock)
{
  net_socket = sock;
}

void gui_remove_net_input(void)
{
  net_socket = -1;
}

void gui_real_conn_list_dialog_update(void *unused)
{
}
