/* Original easing predicates unchanged; MIT, see LICENSE. */
#include <stdio.h>
#include "portable_algorithms/easing.h"
static unsigned assertions,failures;
#define CHECK(cond) do { assertions++; if(!(cond)){fprintf(stderr,"FAIL line%d %s\n",__LINE__,#cond);failures++;} }while(0)
static const uint8_t LINEAR[4]={0,0,255,255};
static const uint8_t EASE[4]={107,0,148,255};
static void test_easing(void) {
    CHECK(cfw_ease_progress(0, LINEAR) == 0);
    CHECK(cfw_ease_progress(32768, LINEAR) == 32768);
    uint32_t mid = cfw_ease_progress(16384, LINEAR);
    CHECK(mid > 16384 - 64 && mid < 16384 + 64);
    uint32_t q = cfw_ease_progress(8192, EASE);           /* ease-in-out starts slow */
    CHECK(q < 6000);
    uint32_t prev = 0;
    for (uint32_t u = 0; u <= 32768; u += 512) {          /* monotonic */
        uint32_t v = cfw_ease_progress(u, EASE);
        CHECK(v >= prev);
        prev = v;
    }
}

int main(void){test_easing();printf("ported easing: %u original assertion evaluations, %u failures\n",assertions,failures);return failures?1:0;}
