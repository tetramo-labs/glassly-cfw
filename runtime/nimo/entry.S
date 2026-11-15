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

/* Input gate. The stock UI dispatcher (0x04208dd2, UI task) jumps here from
 * its entry with `auipc t1; jalr x0` in place of `c.addi16sp sp,-128;
 * c.swsp s0,120(sp); c.swsp s1,116(sp); c.swsp s3,108(sp)`, so a0 = message
 * id, a1 = parameter bytes, a2 = their length and ra = the dispatcher's
 * caller. While the runtime owns the panel, touch messages (0x88..0x8c tap
 * gestures, 0x98 press, 0x99 release) and the auto-brightness step (0xa8) go
 * to glassly_input first; when it returns nonzero the dispatcher never sees
 * them. Everything else, and every
 * message while not owned, replays the four instructions and rejoins. */
    .balign 4
    .globl glassly_input_gate
glassly_input_gate:
    li      t0, NIMO_RAM_BASE
    lbu     t1, NIMO_RAM_OWNED(t0)
    beqz    t1, 6f
    addi    t1, a0, -0x88
    sltiu   t2, t1, 5
    bnez    t2, 5f
    addi    t1, a0, -0x98
    sltiu   t2, t1, 2
    bnez    t2, 5f
    li      t2, 0xa8
    bne     a0, t2, 6f
5:  addi    sp, sp, -16
    sw      ra, 12(sp)
    sw      a0, 8(sp)
    sw      a1, 4(sp)
    sw      a2, 0(sp)
    call    glassly_input
    mv      t0, a0
    lw      ra, 12(sp)
    lw      a0, 8(sp)
    lw      a1, 4(sp)
    lw      a2, 0(sp)
    addi    sp, sp, 16
    beqz    t0, 6f
    ret
6:  addi    sp, sp, -128
    sw      s0, 120(sp)
    sw      s1, 116(sp)
    sw      s3, 108(sp)
    li      t1, 0x04208dda
    jr      t1

/* Notification intake gate. The stock ANCS attribute handler (0x04273e38)
 * calls ancs_intake at 0x04274006 with `auipc ra; jalr ra` in place of
 * `jal ra,0x0428c846; li a2,0x1ca`, so a0 = the intake struct and ra =
 * 0x0427400e. While the phone holds the relay lease the notification goes
 * to it and the stock intake never runs; otherwise the stock intake is
 * called as before. Either way the displaced `li a2,0x1ca` is replayed. */
    .balign 4
    .globl glassly_ancs_intake_gate
glassly_ancs_intake_gate:
    addi    sp, sp, -16
    sw      ra, 12(sp)
    sw      a0, 8(sp)
    call    glassly_ancs_intake
    bnez    a0, 9f
    lw      a0, 8(sp)
    li      t1, 0x0428c846
    jalr    ra, t1, 0
9:  lw      ra, 12(sp)
    addi    sp, sp, 16
    li      a2, 0x1ca
    ret

/* Whitelist gate. The stock ANCS app whitelist check (0x042767d0, a0 = app
 * id) jumps here from its entry with `auipc t1; jalr x0` in place of
 * `c.addi sp,-16; c.swsp s0,8(sp); c.swsp s1,4(sp); c.swsp ra,12(sp)`.
 * Under the relay lease every app is allowed, so the phone's own filter
 * decides; otherwise the four instructions are replayed and the stock check
 * continues at 0x042767d8. */
    .balign 4
    .globl glassly_ancs_whitelist_gate
glassly_ancs_whitelist_gate:
    addi    sp, sp, -32
    sw      ra, 28(sp)
    sw      a0, 24(sp)
    call    glassly_ancs_leased
    mv      t0, a0
    lw      a0, 24(sp)
    lw      ra, 28(sp)
    addi    sp, sp, 32
    beqz    t0, 10f
    li      a0, 1
    ret
10: addi    sp, sp, -16
    sw      s0, 8(sp)
    sw      s1, 4(sp)
    sw      ra, 12(sp)
    li      t1, 0x042767d8
    jr      t1
