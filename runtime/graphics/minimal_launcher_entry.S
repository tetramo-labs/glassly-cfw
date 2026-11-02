/* Native callback callers may supply only eight-byte stack alignment. */
.option norelax
.macro LAUNCHER_ENTRY name
.section .text.\name\()_entry,"ax",@progbits
.align 1
.global \name\()_entry
.type \name\()_entry,@function
\name\()_entry:
    mv t0,sp
    andi sp,sp,-16
    addi sp,sp,-16
    sw t0,0(sp)
    sw ra,4(sp)
    call \name
    lw t0,0(sp)
    lw ra,4(sp)
    mv sp,t0
    ret
.size \name\()_entry,.-\name\()_entry
.endm
LAUNCHER_ENTRY glassly_launcher_init
LAUNCHER_ENTRY glassly_launcher_destroy
LAUNCHER_ENTRY glassly_launcher_tick
LAUNCHER_ENTRY glassly_launcher_event
LAUNCHER_ENTRY glassly_launcher_message
LAUNCHER_ENTRY glassly_launcher_home
LAUNCHER_ENTRY glassly_launcher_suspend
