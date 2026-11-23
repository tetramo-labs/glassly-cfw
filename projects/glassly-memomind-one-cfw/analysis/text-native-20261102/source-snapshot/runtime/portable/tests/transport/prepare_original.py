#!/usr/bin/env python3
"""Rebind unchanged original transport assertions to production mm_transport."""
from pathlib import Path
import argparse
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
def prepare():
    text=(REPO/'tests/g2_compat/upstream/patches/host/transport_host_test.c').read_text()
    text=text.replace('#include "utils.c"\n#include "memory.h"','#include <string.h>\n#include "transport.h"\n#include "compat_constants.h"\nstatic uint16_t rd16(const uint8_t *p) { return (uint16_t)(p[0]|((uint16_t)p[1]<<8)); }\n#define bzero(p,n) memset(p,0,n)')
    text=text.replace('#include "cfw_context.h"','typedef mm_transport customCfwContext;\ntypedef mm_transport_stream cfw_message_stream;')
    text=text.replace('#include "message_transport.c"','#include "original_adapter.h"')
    old='''        for (unsigned o = 0; o < 2; o++) {
            cfw_message_stream *s = &g_ctx[l].message_streams[o];
            cfw_inflate_reset(s);
            cfw_message_discard(s);
        }
        bzero((uint8_t *)&g_ctx[l], sizeof g_ctx[l]);'''
    assert old in text
    text=text.replace(old,'''        mm_transport_dispose(&g_ctx[l]);
        initialize_context(&g_ctx[l], (uint8_t)(l+1));''')
    return '/* Generated test-only G2 wire/topology fixture binding; see prepare_original.py. */\n'+text
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
    path=HERE/'transport_host_test.c';text=prepare()
    if a.check:
        if not path.exists() or path.read_text()!=text:raise SystemExit('original transport binding stale')
    else:path.write_text(text)
