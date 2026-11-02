/* Stock tasks enter with only8-byte SP alignment. Preserve native gp/tp and
 * caller frame; C sees16-byte alignment. No new task-return/delete convention. */
.option norelax
.section .text.flash_canary_entry,"ax",@progbits
.align 1
.global glassly_flash_canary_entry
.type glassly_flash_canary_entry,@function
glassly_flash_canary_entry:
    mv t0,sp
    andi sp,sp,-16
    addi sp,sp,-16
    sw t0,0(sp)
    sw ra,4(sp)
    sw s0,8(sp)
    call glassly_flash_canary_worker
    lw t0,0(sp)
    lw ra,4(sp)
    lw s0,8(sp)
    mv sp,t0
    ret
.size glassly_flash_canary_entry,.-glassly_flash_canary_entry
.section .text.flash_canary_dispatch,"ax",@progbits
.align 1
.global glassly_flash_canary_dispatch
.type glassly_flash_canary_dispatch,@function
glassly_flash_canary_dispatch:
    li t0,0x7a
    beq a0,t0,glassly_flash_canary_command_entry
    j glassly_flash_read_command
.size glassly_flash_canary_dispatch,.-glassly_flash_canary_dispatch

/* Only new cmd7a gets a service ABI realignment. All other gates keep their
 * existing stack/RA behavior. a0..a3 include the original response pointer. */
.section .text.flash_canary_command_entry,"ax",@progbits
.align 1
.global glassly_flash_canary_command_entry
.type glassly_flash_canary_command_entry,@function
glassly_flash_canary_command_entry:
    mv t0,sp
    andi sp,sp,-16
    addi sp,sp,-16
    sw t0,0(sp)
    sw ra,4(sp)
    sw s0,8(sp)
    call glassly_flash_canary_command
    lw t0,0(sp)
    lw ra,4(sp)
    lw s0,8(sp)
    mv sp,t0
    ret
.size glassly_flash_canary_command_entry,.-glassly_flash_canary_command_entry
