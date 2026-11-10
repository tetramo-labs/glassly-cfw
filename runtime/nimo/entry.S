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
