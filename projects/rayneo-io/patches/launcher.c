/* CFW v14: no stock launcher while a phone is linked.
 *
 * ViewManager::onEnterState hides every view, then shows the one its state
 * names: the app list (the crown carousel of RayNeo apps) through its one
 * `bl AppListView::show`, the board (RayNeo's dashboard cards) through its one
 * `bl BoardView::show`. Both calls come here. While the launcher's LinkMonitor
 * reports the phone connected they stay hidden (the app list's crown-wheel
 * listener unregistered) and the screen stays black until the Glassly page
 * takes it. Unlinked they show as stock, so the disconnected, setup and pairing
 * views (other states, other views) are untouched.
 * Verified by disassembly of Strix OS 1.0.4.12; byte-checked by build.py. */
#include "cfw.h"

int cfw_link_up(void) {
    const uint8_t *monitor = (const uint8_t *)fw_link_monitor();
    return monitor && *(const volatile uint8_t *)(monitor + LINK_MONITOR_CONNECTED) != 0;
}

void cfw_applist_show(void *view) {
    if (cfw_link_up()) return;
    fw_applist_show(view);
}

void cfw_board_show(void *view) {
    if (cfw_link_up()) return;
    fw_board_show(view);
}
