.option norelax
.section .text.glassly_microphone_task_entry,"ax",@progbits
.align 1
.global glassly_microphone_task_entry
.type glassly_microphone_task_entry,@function
glassly_microphone_task_entry:
    mv t0,sp
    andi sp,sp,-16
    addi sp,sp,-16
    sw t0,0(sp)
    sw ra,4(sp)
    call glassly_microphone_task
    lw ra,4(sp)
    lw t0,0(sp)
    mv sp,t0
    ret
.size glassly_microphone_task_entry,.-glassly_microphone_task_entry

.macro save_arguments
    mv t0,sp
    andi sp,sp,-16
    addi sp,sp,-48
    sw t0,0(sp)
    sw ra,4(sp)
    sw a0,8(sp)
    sw a1,12(sp)
    sw a2,16(sp)
    sw a3,20(sp)
    sw a4,24(sp)
    sw a5,28(sp)
    sw a6,32(sp)
    sw a7,36(sp)
.endm
.macro restore_arguments
    lw a0,8(sp)
    lw a1,12(sp)
    lw a2,16(sp)
    lw a3,20(sp)
    lw a4,24(sp)
    lw a5,28(sp)
    lw a6,32(sp)
    lw a7,36(sp)
    lw ra,4(sp)
    lw t0,0(sp)
    mv sp,t0
.endm
.macro tx_gate name,callback,continuation,b0,b1,b2,b3,b4,b5,b6,b7
.section .text.\name,"ax",@progbits
.align 1
.global \name
.type \name,@function
\name:
    save_arguments
    call \callback
    beqz a0,1f
    restore_arguments
    .byte \b0,\b1,\b2,\b3,\b4,\b5,\b6,\b7
    li t0,\continuation
    jr t0
1:
    lw ra,4(sp)
    lw t0,0(sp)
    mv sp,t0
    li a0,0
    ret
.size \name,.-\name
.endm
tx_gate glassly_microphone_spp_entry,glassly_microphone_spp,0x0431caa6,0x1d,0x71,0x86,0xce,0xa2,0xcc,0xa6,0xca
tx_gate glassly_microphone_iap2_entry,glassly_microphone_iap2,0x0431b894,0x79,0x71,0x06,0xd6,0x22,0xd4,0x26,0xd2

.section .text.glassly_microphone_link_entry,"ax",@progbits
.align 1
.global glassly_microphone_link_entry
.type glassly_microphone_link_entry,@function
glassly_microphone_link_entry:
    save_arguments
    call glassly_microphone_link
    restore_arguments
    .byte 0x01,0x11,0x26,0xca,0xb7,0x44,0x01,0x02
    li t0,0x04245cfc
    jr t0
.size glassly_microphone_link_entry,.-glassly_microphone_link_entry
