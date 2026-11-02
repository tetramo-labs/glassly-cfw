/* Link-only C entry fixtures for gate emulation, not a graphics runtime.
 * The harness observes these entry boundaries before the fixture bodies run.
 */
#include <stdint.h>
__attribute__((noinline))
void glassly_graphics_probe(uint32_t cmd, void *request, const uint8_t *sequence, void **response)
{ __asm__ volatile("" : : "r"(cmd), "r"(request), "r"(sequence), "r"(response)); }
__attribute__((noinline))
void glassly_graphics_command(uint32_t cmd, void *request, const uint8_t *sequence, void **response)
{ __asm__ volatile("" : : "r"(cmd), "r"(request), "r"(sequence), "r"(response)); }
__attribute__((noinline))
void glassly_graphics_display(void *envelope)
{ __asm__ volatile("" : : "r"(envelope)); }
