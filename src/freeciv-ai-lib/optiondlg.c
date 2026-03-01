#ifdef HAVE_CONFIG_H
#include <fc_config.h>
#endif

/* utility */
#include "log.h"

/* gui main header */
//#include "gui_stub.h"

#include "optiondlg.h"


void option_dialog_popup(const char *name, const struct option_set *poptset)
{
    /* log_normal("STUB: option_dialog_popup(%s, %p)", name, poptset); */
}

void option_dialog_popdown(const struct option_set *poptset)
{
    /* log_normal("STUB: option_dialog_popdown(%p)", poptset); */
}

void option_gui_update(struct option *poption)
{
    /* log_normal("STUB: option_gui_update(%p)", poption); */
}

void option_gui_add(struct option *poption)
{
    /* log_normal("STUB: option_gui_add(%p)", poption); */
}

void option_gui_remove(struct option *poption)
{
    /* log_normal("STUB: option_gui_remove(%p)", poption); */
}
