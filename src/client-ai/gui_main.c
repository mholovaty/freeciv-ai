#ifdef HAVE_CONFIG_H
#include <fc_config.h>
#endif

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <libgen.h>

/* utility */
#include "fc_cmdline.h"
#include "fciconv.h"
#include "log.h"

/* client */
#include "gui_cbsetter.h"
#include "client_main.h"
#include "editgui_g.h"
#include "options.h"

const char *client_string = "client-ai";

const char * const gui_character_encoding = "UTF-8";
const bool gui_use_transliteration = FALSE;

void gui_ui_init(void)
{

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

int main(int argc, char **argv)
{
  set_data_path();

  setup_gui_funcs();
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

  log_normal(_("Freeciv AI Client started"));

  return EXIT_SUCCESS;
}

void gui_ui_exit(void)
{

}
