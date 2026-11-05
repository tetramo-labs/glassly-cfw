#ifndef ZERO2_BUTTON_INPUT_H
#define ZERO2_BUTTON_INPUT_H

#include <stdint.h>

/* Recovered stock mask bits; physical button labels are still unverified. */
#define Z2_INPUT_MASK UINT32_C(0x3ff9)
#define Z2_INPUT_COUNT 12u
#define Z2_DEBOUNCE_MS 8u

struct z2_input {
    uint32_t changed_at[Z2_INPUT_COUNT];
    uint16_t candidate, stable;
};

/* Unbound component: no GPIO, timer or firmware address is accessed here.
 * Reset on boot and when the clock restarts or sampling resumes after sleep.
 * Initial state is released; held buttons qualify after the debounce window. */
void z2_input_reset(struct z2_input *input);

/* One owner samples raw stock GPIO masks with a monotonic millisecond clock.
 * uint32_t clock wrap is supported; reset if a full clock period is skipped.
 * Each bit must remain unchanged in observed samples for 8 ms before commit.
 * Shorter pulses are intentionally filtered. Poll regularly (planned <=1 ms);
 * behavior between observations cannot be inferred. Never pass the stock
 * 0xffffffff no-change sentinel as raw GPIO: sample the actual mask instead.
 * Returns a complete debounced mask, ready for z2_stream_poll(). */
uint32_t z2_input_poll(struct z2_input *input, uint32_t raw, uint32_t now_ms);

#endif
