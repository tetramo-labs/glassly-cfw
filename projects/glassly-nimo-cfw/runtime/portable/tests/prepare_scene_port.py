#!/usr/bin/env python3
"""Reproduce adapted scene core and unmodified original assertion bodies."""
from pathlib import Path
import hashlib
import json
import os
import re
import sys
ROOT=Path(__file__).resolve().parents[1]
# The pinned G2 reference is read in place (never copied here): the MemoMind
# repository bundles it. Override with GLASSLY_G2_REFERENCE=<upstream dir>.
REFERENCE=Path(os.environ.get('GLASSLY_G2_REFERENCE') or Path.home()/'dev/glassly-memomind-one-cfw/tests/g2_compat/upstream')
SRC=REFERENCE/'patches'
NOTICE='/* Derived from pinned G2 commite889569fe77775ed5822af6f7e47210f2984f15d.\n * Explicit MemoMind platform adaptation; MIT, see PROVENANCE.md. */\n'

def emit(path,text):
    # Explicit optional-backend overlay: original upstream generation remains
    # pinned and reproducible; no original test predicate is rewritten.
    overlay=ROOT/'tests/scene_store/generated-overlay.json'
    if overlay.exists() and path.name in ('scene_internal.h','scene_shapes.inc','scene_cache.inc'):
        entry=json.loads(overlay.read_text())[path.name]
        if hashlib.sha256(text.encode()).hexdigest()!=entry['base_sha256']:
            raise RuntimeError('External-store overlay base drift: '+path.name)
        lines=text.splitlines(keepends=True)
        for hunk in reversed(entry['hunks']):
            a,b=hunk['start'],hunk['end']
            if lines[a:b]!=hunk['before']:raise RuntimeError('Overlay hunk drift: '+path.name)
            lines[a:b]=hunk['after']
        text=''.join(lines)
        if hashlib.sha256(text.encode()).hexdigest()!=entry['result_sha256']:
            raise RuntimeError('External-store overlay result drift: '+path.name)
    # Native scratch policy is a separate opt-in adaptation. Keep the external
    # backend overlay and every upstream assertion untouched.
    if path.name == 'scene_cache.inc':
        anchor = 'static int cfw_txn_snapshot(cfw_txn *t) {\n    cfw_undo *undo = t->sc->undo;\n'
        if text.count(anchor) != 1:
            raise RuntimeError('RESET undo policy anchor drift')
        text = text.replace(anchor, anchor + "#ifdef MM_SCENE_RESET_UNDO_TRIM\n    /* Native opt-in: RESET releases scratch, so reacquisition can fail. Refuse\n     * before pinning/evicting/staging instead of entering revision50's no-undo\n     * fallback. The default portable G2 policy remains unchanged. */\n    if (!undo) return cfw_txn_fail(t, CFW_CACHE_REPLY_CAPACITY, 0);\n#endif\n", 1)
    # Per-eye rendering is a separate native opt-in: an object id with bit 31
    # belongs to one eye (bit 30: 0 left, 1 right) and a render with ctx->eye
    # set skips the other eye's objects. Ids without bit 31 draw in both.
    if path.name == 'scene_cache.inc':
        anchor = '        if (o->id == 0 || !(o->flags & CFW_SHAPE_FLAG_VISIBLE)) continue;\n        cfw_box box;\n'
        if text.count(anchor) != 1:
            raise RuntimeError('Stereo eye filter anchor drift')
        text = text.replace(anchor, '        if (o->id == 0 || !(o->flags & CFW_SHAPE_FLAG_VISIBLE)) continue;\n#ifdef MM_SCENE_STEREO_EYES\n        if ((o->id >> 31) && ctx->eye && ((o->id >> 30) & 1u) + 1u != ctx->eye) continue;\n#endif\n        cfw_box box;\n', 1)
    # Capacities a native build may override (NIMO: 64 KiB, 128, 128). Without
    # the defines the upstream values stand.
    if path.name == 'scene_internal.h':
        for name in ('CFW_TEXTURE_CACHE_SIZE', 'CFW_CACHE_OBJECTS', 'CFW_CACHE_ASSETS'):
            found = re.findall(r'^#define '+name+r'\b.*\n', text, re.M)
            if len(found) != 1:
                raise RuntimeError('Capacity anchor drift: '+name)
            text = text.replace(found[0], '#ifndef '+name+'\n'+found[0]+'#endif\n', 1)
    if '--check' in sys.argv:
        if path.read_text()!=text:raise RuntimeError('Generated scene source drift: '+str(path))
    else:path.write_text(text)


def main():
    # Internal data layouts retain original fields; owner carries explicit context.
    head=(SRC/'scene.h').read_text();head=head[head.index('/* ---- Retained'):]
    head=head.replace('    uint32_t magic;\n    uint8_t *fb;', '    uint32_t magic;\n    mm_scene_context *owner;\n    uint8_t *fb;')
    head=head.replace('void scene_tick(void *arg);','static void scene_tick(void *arg);')
    sh=(SRC/'shapes.h').read_text();sh=sh[sh.index('/* ---- Shape records'):]
    sh=sh[:sh.index('static uint32_t cfw_shape_record_len')]
    vh=(SRC/'vector.h').read_text();vh=vh[vh.index('/* Revision'):vh.index('/* Heap workspace')]
    # The compiled path layout is exactly the portable vector ABI.
    vh=vh.replace('typedef struct { int32_t x0, y0, x1, y1; } cfw_edge;','typedef mm_vector_edge cfw_edge;')
    a=vh.index('typedef struct {\n    uint16_t count;');b=vh.index('typedef struct {\n    int32_t angle',a)
    vh=vh[:a]+'typedef mm_vector_path cfw_path;\n'+vh[b:]
    th=(SRC/'texture_cache.h').read_text();th=th[th.index('/* Capacity'):]
    th=th[:th.index('static int cfw_builtin_draw_string(')]
    emit(ROOT/'scene_internal.h',NOTICE+'#ifndef MM_SCENE_INTERNAL_H\n#define MM_SCENE_INTERNAL_H\n#include "scene.h"\n'+
        'typedef mm_scene_context customCfwContext;\n#define CFW_REPLY_HDR_SIZE 5u\ntypedef mm_scene_dirty cfw_rectlist;\n#define CFW_RECT_MAX MM_SCENE_RECT_MAX\n#define CFW_CTX_MAGIC MM_SCENE_MAGIC\n'+vh+
        '\ntypedef mm_vector_work cfw_vector_work;\n'+sh+th+head+'\n#endif\n')
    asset=(SRC/'texture_cache.c').read_text()
    a=asset.index('/* Decode one RLE token');b=asset.index('static uint32_t cfw_texture_next_glyph')
    asset=asset[a:b].replace(' || !cfw_fb_lease_active()', '')
    emit(ROOT/'scene_assets.inc',NOTICE+'#define CFW_TEXTURE_OPT_TRANSPARENT 0x10u\n#define CFW_TEXTURE_OPT_INVERSE 0x20u\n'+asset)
    shapes=(SRC/'shapes.c').read_text();a=shapes.index('/* Which parameters are x / y');b=shapes.index('/* IMAGE/TEXT records')
    emit(ROOT/'scene_shapes.inc',NOTICE+shapes[a:b])
    core=(SRC/'scene.c').read_text();core=core[core.index('/* ---- Retained object cache'):]
    core=core.replace('sc->magic = CFW_CACHE_MAGIC;','sc->magic = CFW_CACHE_MAGIC;\n    sc->owner = ctx;')
    core=core.replace('cfw_malloc(sizeof(cfw_cache))','mm_scene_allocate(ctx, MM_SCENE_PERSISTENT, sizeof(cfw_cache))')
    core=core.replace('cfw_malloc(sizes[i])','mm_scene_allocate(ctx, MM_SCENE_PERSISTENT, sizes[i])')
    core=core.replace('            uint8_t *store =','            if (sizes[i] > ctx->store_limit) continue;\n            uint8_t *store =')
    core=core.replace('FW_FREE(store)','mm_scene_deallocate(ctx, MM_SCENE_PERSISTENT, store)')
    core=core.replace('FW_FREE(sc->undo)','mm_scene_deallocate(sc->owner, MM_SCENE_PERSISTENT, sc->undo)')
    core=core.replace('FW_FREE(sc)','mm_scene_deallocate(ctx, MM_SCENE_PERSISTENT, sc)')
    core=core.replace('cfw_heap13_free(sc->vector_work)','mm_scene_deallocate(ctx, MM_SCENE_WORKSPACE, sc->vector_work)')
    core=core.replace('cfw_malloc(sizeof(cfw_undo) + capacity * sizeof(undo->granules[0]))','mm_scene_allocate(sc->owner, MM_SCENE_PERSISTENT, sizeof(cfw_undo) + capacity * sizeof(undo->granules[0]))')
    core=core.replace('cfw_heap13_malloc(sizeof(cfw_vector_work))','mm_scene_allocate(ctx, MM_SCENE_WORKSPACE, sizeof(cfw_vector_work))')
    core=core.replace('sc->fb = cfw_shadow_buffer();','sc->fb = mm_scene_shadow(sc->owner);')
    core=core.replace('cfw_shadow_buffer()', 'mm_scene_shadow(ctx)')
    core=core.replace('FW_TIMER_STOP(ctx->scene_timer)','mm_scene_timer_stop(ctx)')
    core=core.replace('FW_TIMER_START(ctx->scene_timer, sc->period_ms)','mm_scene_timer_start(ctx, sc->period_ms)')
    core=core.replace('FW_TIMER_NEW(CFW_FN_ADDR(scene_tick), 0, ctx, 0)','mm_scene_timer_new(ctx)')
    core=core.replace('FW_DISPLAY_WAIT()','mm_scene_gate_wait(ctx)').replace('FW_DISPLAY_SIGNAL()','mm_scene_gate_signal(ctx)')
    core=core.replace('cfw_fb_lease_active()','mm_scene_lease(ctx)')
    core=core.replace('cfw_message_reply_capacity_hint(', 'mm_scene_reply_capacity_hint(ctx, ')
    core=core.replace('static void cfw_object_freeze(cfw_object *o) {\n    uint32_t now = FW_MS_TICK;', 'static void cfw_object_freeze(cfw_object *o, uint32_t now) {')
    core=core.replace('cfw_object_freeze(o);','cfw_object_freeze(o, mm_scene_now(sc->owner));')
    core=core.replace('cfw_object_freeze(&sc->objects[sc->active[i]]);','cfw_object_freeze(&sc->objects[sc->active[i]], mm_scene_now(ctx));')
    # All clock reads except scene_advance have ctx; advance uses cache owner.
    core=core.replace('uint32_t now = FW_MS_TICK;', 'uint32_t now = mm_scene_now(sc->owner);')
    core=core.replace('FW_MS_TICK','mm_scene_now(ctx)')
    core=core.replace('case CFW_OP_FREEZE:\n        cfw_object_freeze(o, mm_scene_now(sc->owner));','case CFW_OP_FREEZE:\n        cfw_object_freeze(o, clock->now);')
    core=core.replace('cfw_raster r = { fb, IMAGE_STRIDE, (int32_t)IMAGE_W, (int32_t)IMAGE_H };',
        'cfw_raster r = { fb, ctx->raster.stride, (int32_t)ctx->raster.width, (int32_t)ctx->raster.height };')
    core=core.replace('rl_add(rl, 0, 0, IMAGE_W, IMAGE_H);','rl_add(rl, 0, 0, ctx->raster.width, ctx->raster.height);')
    core=core.replace('cv_path_draw(&r, sc->vector_work, path, o->p, &o->rotation, o->color);',
        'mm_scene_path_draw(&r, sc->vector_work, path, o->p, &o->rotation, o->color);')
    core=core.replace('cv_shape_draw(&r, sc->vector_work, &s, &o->rotation, rl);',
        'mm_scene_shape_draw(ctx, &r, sc->vector_work, &s, &o->rotation, rl);')
    core=core.replace('cfw_shape_draw(&r, &s, rl);','mm_scene_shape_draw(ctx, &r, 0, &s, 0, rl);')
    # Revision 51 partial render: the panel box and the clipped view come from the owner's raster.
    core=core.replace('int32_t pw = (int32_t)IMAGE_W, ph = (int32_t)IMAGE_H;',
        'int32_t pw = (int32_t)ctx->raster.width, ph = (int32_t)ctx->raster.height;')
    core=core.replace('cfw_raster r = { fb + (uint32_t)dirty.t * IMAGE_STRIDE + ((uint32_t)dirty.l >> 1), IMAGE_STRIDE, dirty.r - dirty.l, dirty.b - dirty.t };',
        'cfw_raster r = { fb + (uint32_t)dirty.t * ctx->raster.stride + ((uint32_t)dirty.l >> 1),\n                     ctx->raster.stride, dirty.r - dirty.l, dirty.b - dirty.t };')
    core=core.replace('cv_path_draw(&r, sc->vector_work, path, s.p, &rot, o->color);',
        'mm_scene_path_draw(&r, sc->vector_work, path, s.p, &rot, o->color);')
    core=core.replace('cv_shape_draw(&r, sc->vector_work, &s, &rot, &scratch);',
        'mm_scene_shape_draw(ctx, &r, sc->vector_work, &s, &rot, &scratch);')
    core=core.replace('cfw_shape_draw(&r, &s, &scratch);','mm_scene_shape_draw(ctx, &r, 0, &s, 0, &scratch);')
    core=core.replace('cv_compile(w, s.text, (uint16_t)s.p[3])','mm_vector_compile(w, sizeof(*w), s.text, (uint16_t)s.p[3], s.width, 0, 0)')
    core=core.replace('void scene_tick(void *arg) {','static void scene_tick(void *arg) {')
    core=core.replace('path->edges[i] = w->edges[i];','memcpy(&path->edges[i], &w->edges[i], sizeof(cfw_edge));')
    emit(ROOT/'scene_cache.inc',NOTICE+core)

    # Preserve original helper/test bodies; replace only platform setup and bind
    # the explicit context after original test resets. Assertion text is untouched.
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    from csource import function, predicates
    original=(SRC/'host/shapes_host_test.c').read_text()
    prefix=original[original.index('static customCfwContext g_ctx;'):original.index('/* The real image/font')]
    prefix=prefix.replace(function(original,'rl_add')[0], '')
    font=function(original,'stub_box')[0]+'\n'+function(original,'cfw_builtin_draw_string_buf')[0].replace('cfw_builtin_draw_string_buf','test_builtin_draw_string_buf')
    body=original[original.index('/* ---- helpers'):]
    body=body.replace('#define CHECK(cond) do { if', 'static unsigned long long mm_test_checks;\n#define CHECK(cond) do { mm_test_checks++; if')
    body=body.replace('g_ctx.magic = CFW_CTX_MAGIC;', 'g_ctx.magic = CFW_CTX_MAGIC; test_bind();')
    body=body.replace('int main(int argc, char **argv) {','int main(int argc, char **argv) { test_bind();')
    preamble=NOTICE+'#include <stdint.h>\n#include <stdio.h>\n#include <stdlib.h>\n#include "../../scene_internal.h"\n#define IMAGE_W 640u\n#define IMAGE_H 480u\n#define IMAGE_STRIDE 320u\n#define IMAGE_BYTES (IMAGE_STRIDE*IMAGE_H)\nstatic uint32_t g_now;\n#define FW_MS_TICK g_now\nstatic void bzero(uint8_t *,uint32_t);\nstatic uint32_t rd16(const uint8_t *);\n'
    generated=preamble+prefix+'\n'+font+'\nstatic uint8_t g_hint;\nstatic int g_settled;static uint16_t g_settled_tag;\n#include "platform.inc"\n'+body
    emit(ROOT/'tests/scene/shapes_host_test.c',generated)
    vector=(SRC/'host/vector_host_test.c').read_text()
    vector=vector.replace('    return (g_fail || g_alloc_live)?1:0;', '    printf("portable original CHECK evaluations: %llu\\n",mm_test_checks);\n    return (g_fail || g_alloc_live)?1:0;')
    vector=vector.replace('int main(int argc,char **argv) {', 'int main(int argc,char **argv) { test_bind();')
    vector=vector.replace('g_ctx.magic=CFW_CTX_MAGIC;', 'g_ctx.magic=CFW_CTX_MAGIC;test_bind();')
    emit(ROOT/'tests/scene/vector_host_test.c',NOTICE+vector)
    for name,text in [('shapes_host_test.c',generated),('vector_host_test.c',vector)]:
        expected=[p['expression'] for p in predicates((SRC/'host'/name).read_text(),('CHECK',))]
        actual=[p['expression'] for p in predicates(text,('CHECK',))]
        if expected!=actual:raise RuntimeError('Original assertions changed: '+name)

if __name__=='__main__':main()
