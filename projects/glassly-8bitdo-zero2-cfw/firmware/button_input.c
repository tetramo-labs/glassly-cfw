#include "button_input.h"

_Static_assert(sizeof(struct z2_input) == 52, "Review RAM reservation on layout change");

void z2_input_reset(struct z2_input *s) {
    s->candidate = s->stable = 0;
    for (unsigned i = 0; i < Z2_INPUT_COUNT; ++i) s->changed_at[i] = 0;
}

uint32_t z2_input_poll(struct z2_input *s, uint32_t raw, uint32_t now_ms) {
    unsigned index = 0;
    raw &= Z2_INPUT_MASK;
    for (uint32_t bit = 1; bit <= UINT32_C(0x2000); bit <<= 1) {
        if (!(Z2_INPUT_MASK & bit)) continue;
        if ((raw ^ s->candidate) & bit) {
            s->candidate ^= (uint16_t)bit;
            s->changed_at[index] = now_ms;
        } else if (((s->candidate ^ s->stable) & bit) &&
                   (uint32_t)(now_ms - s->changed_at[index]) >= Z2_DEBOUNCE_MS) {
            s->stable ^= (uint16_t)bit;
        }
        ++index;
    }
    return s->stable;
}
