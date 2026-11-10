#include "ram.h"

/* Router gate. The stock command router (0x0426dfa8) jumps here from its
 * unrouted branch (0x0426e02e) with s1=cmd, s2=key, s5=payload, s4=len live.
 * The runtime gets first look; anything it leaves goes on to the stock
 * NOT_SUPPORTED reply exactly as before. */
    .section .text.entry, "ax"
    .balign 4
    .globl glassly_router_gate
glassly_router_gate:
    mv      a0, s1
    mv      a1, s2
    mv      a2, s5
    mv      a3, s4
    call    glassly_command
    bnez    a0, 1f
    /* the 8 bytes the hook replaced, then the stock unrouted path */
    lui     a2, 0x4378
    mv      a4, s2
    mv      a5, s4
    li      t1, 0x0426e036
    jr      t1
1:  /* handled: leave through the router's own epilogue */
    li      t1, 0x0426e112
    jr      t1

/* Flush gate. The frame task's only panel write (0x041fd63c) calls here with
 * `auipc ra; jalr ra` in place of `c.mv a4,s2; c.li s3,0; c.lw a5,16(a5);
 * c.jalr a5`, so ra = 0x041fd644 and a0..a3 hold the flush arguments. Replays
 * the two register moves, then either tail-calls the panel op (stock path) or,
 * while the runtime owns the panel, reports the rows as sent without writing
 * them; the frame task's own bookkeeping runs on unchanged. Only temporaries
 * the call would clobber anyway are used. */
    .balign 4
    .globl glassly_flush_gate
glassly_flush_gate:
    mv      a4, s2
    li      s3, 0
    li      t0, NIMO_RAM_BASE
    lbu     t1, NIMO_RAM_OWNED(t0)
    bnez    t1, 2f
    lw      a5, 16(a5)
    jr      a5
2:  lw      t1, NIMO_RAM_GATE_SKIPS(t0)
    addi    t1, t1, 1
    sw      t1, NIMO_RAM_GATE_SKIPS(t0)
    li      t1, NIMO_LIT_FLAG
    li      t2, 1
    sb      t2, 0(t1)
    li      t1, NIMO_BLANK_TICKS
    sw      zero, 0(t1)
    li      a0, 0
    ret

/* Kick gate. The frame kick (0x041f703c) jumps here from its entry with
 * `auipc t1; jalr x0` in place of `lbu a5,1157(gp); c.beqz a5,0x041f705c;
 * c.addi sp,-32`, so ra is still the kick's caller. While the runtime owns
 * the panel the kick does nothing and reports success: no commit, so the
 * stock framebuffer indices stay pinned and the canvas buffer has no stock
 * writer. Otherwise it replays the three instructions and rejoins the kick.
 * Only temporaries are used, which the kick's callers do not keep. */
    .balign 4
    .globl glassly_kick_gate
glassly_kick_gate:
    li      t0, NIMO_RAM_BASE
    lbu     t1, NIMO_RAM_OWNED(t0)
    bnez    t1, 4f
    lbu     a5, 1157(gp)
    beqz    a5, 3f
    addi    sp, sp, -32
    li      t1, 0x041f7044
    jr      t1
3:  li      t1, 0x041f705c
    jr      t1
4:  lw      t1, NIMO_RAM_GATE_SKIPS(t0)
    addi    t1, t1, 1
    sw      t1, NIMO_RAM_GATE_SKIPS(t0)
    li      a0, 0
    ret
