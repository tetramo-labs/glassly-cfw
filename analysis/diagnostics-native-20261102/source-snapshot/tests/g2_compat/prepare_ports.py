#!/usr/bin/env python3
"""Reproduce the geometry partition of upstream assertions without changing them."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/'upstream/patches/host/shapes_host_test.c'


def generate():
    text=SOURCE.read_text()
    body=text[text.index('static void test_immediate('):text.index('\nstatic void test_easing(')]
    # Preserve exact geometry fixture records and predicates. Unsupported asset
    # groups stay in the unchanged upstream corpus and the unimplemented mapping.
    body=body.replace('test_immediate(', 'test_immediate_ported(',1)
    a=body.index('    fresh();');b=body.index('    uint8_t msg[',a);body=body[:a]+body[b:]
    a=body.index('    p = rec_asset(');b=body.index('    msg[0]',a);body=body[:a]+body[b:]
    a=body.index('    /* the image asset');b=body.index('    /* full pie',a);body=body[:a]+body[b:]
    a=body.index('    put32(msg + len - 16');b=body.index('    { uint8_t cmds[]',a);body=body[:a]+body[b:]
    a=body.index('    /* modes 19/20');body=body[:a]+'}\n'
    body=body.replace('cfw_shapes_immediate(', 'memo_immediate(')
    prefix='''/* Generated from pinned upstream test_immediate; MIT, see LICENSE.
 * Retained original geometric records and assertions; asset/cache portions
 * remain explicitly unimplemented. Run prepare_ports.py to reproduce. */
#define main original_shapes_reference_main
#include "upstream/patches/host/shapes_host_test.c"
#undef main
#include "geometry.h"
#undef CHECK
static unsigned memo_assertions;
#define CHECK(cond) do { memo_assertions++; if (!(cond)) { fprintf(stderr,"FAIL %s:%d %s\\n",__FILE__,__LINE__,#cond); g_fail++; } } while (0)
static int memo_immediate(uint8_t *pixels,uint32_t stride,uint32_t w,uint32_t h,
                          const uint8_t *src,uint32_t len,cfw_rectlist *rl) {
    (void)rl;
    uint8_t packet[MM_GEOMETRY_MAX_MESSAGE];
    if (len + 1u > sizeof(packet)) return -1;
    packet[0]=36;
    for (uint32_t i=0;i<len;i++) packet[i+1]=src[i];
    mm_raster target={pixels,(size_t)stride*h,w,h,stride};
    return mm_geometry_mode36(&target,packet,len+1u)==0 ? 0 : -1;
}
'''
    suffix='''
int main(int argc,char **argv) {
    if(argc!=2) return 2;
    test_immediate_ported(argv[1]);
    printf("ported original geometric partition: %u original assertions, %d failures\\n",memo_assertions,g_fail);
    return g_fail?1:0;
}
'''
    (ROOT/'ported_shapes.c').write_text(prefix+body+suffix)
    return body


if __name__=='__main__':
    body=generate()
    print('Generated ported_shapes.c; original CHECK sites:',body.count('CHECK('))
