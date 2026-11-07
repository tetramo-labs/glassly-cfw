/* Fixed gates for the H001Y 1.0.3.127 graphics construction profile.
 * Ordinary paths preserve the caller's stack, ra, a0..a7 and saved registers.
 * Only t0/t1 are scratch. Optional observer saves volatile state on the stack
 * before its C call, then restores it before forwarding to stock dispatch.
 */
.option norelax
.section .text.service_entry,"ax",@progbits
.align 1
.global service_entry
.type service_entry, @function
service_entry:
    li t0, 0x7e
    beq a0, t0, .Lprobe
    li t0, 0x7d
    beq a0, t0, .Lcommand
#ifdef MM_GRAPHICS_INPUT
    li t0, 0x7c
    beq a0, t0, .Linput_command
#endif
#ifdef MM_FLASH_CANARY
    addi t0,a0,-0x7a
    li t1,1
    bleu t0,t1,.Lflash_read
#elif defined(MM_GRAPHICS_FLASH_READ)
    li t0, 0x7b
    beq a0, t0, .Lflash_read
#endif
#ifdef MM_WAKE_CONTROL
    j wake_service_gate
#else
    li t0, 0x042e4680
    jr t0
#endif
.Lprobe:
    j glassly_graphics_probe
.Lcommand:
    j glassly_graphics_command
#ifdef MM_GRAPHICS_INPUT
.Linput_command:
    j glassly_input_command
#endif
#ifdef MM_GRAPHICS_FLASH_READ
.Lflash_read:
#ifdef MM_FLASH_CANARY
    j glassly_flash_canary_dispatch
#else
    j glassly_flash_read_command
#endif
#endif
.size service_entry, .-service_entry

.section .text.display_entry,"ax",@progbits
.align 1
.global display_gate
.type display_gate, @function
display_gate:
    /* Exact displaced bytes 032504f9; s0 is still the worker's frame. */
    lw a0, -0x70(s0)
    beqz a0, .Lstock_display
    lbu t0, 1(a0)
    andi t0, t0, 0x3f
#ifdef MM_GRAPHICS_INPUT
    li t1, 2
    beq t0, t1, .Linput_button
    li t1, 3
    beq t0, t1, .Linput_imu
#endif
    li t1, 0x3f
    bne t0, t1, .Lstock_display
    lhu t0, 4(a0)
    li t1, 0x474c
    bne t0, t1, .Lstock_display
    j glassly_graphics_display
.Lstock_display:
    li t0, 0x0425b38a
    jr t0
#ifdef MM_GRAPHICS_INPUT
.Linput_button:
    lhu t0, 6(a0)
    bnez t0, .Lstock_display
    lhu t0, 4(a0)
    li t1, 0x1f7b
    sub t0, t0, t1
    li t1, 4
    bleu t0, t1, .Lobserve
    lhu t0, 4(a0)
    li t1, 0x1fb0
    sub t0, t0, t1
    li t1, 9
    bleu t0, t1, .Lobserve
    j .Lstock_display
.Linput_imu:
    lhu t0, 6(a0)
    bnez t0, .Lstock_display
    lhu t0, 4(a0)
    addi t0, t0, -1
    li t1, 7
    bgtu t0, t1, .Lstock_display
.Lobserve:
    /* ilp32f caller-clobbered state: ra, a0..a7, t2..t6, ft/fa, fcsr.
     * No extra stack remains when the stock dispatcher is reached. */
    addi sp, sp, -144
    sw ra, 0(sp)
    sw a0, 4(sp)
    sw a1, 8(sp)
    sw a2, 12(sp)
    sw a3, 16(sp)
    sw a4, 20(sp)
    sw a5, 24(sp)
    sw a6, 28(sp)
    sw a7, 32(sp)
    sw t2, 36(sp)
    sw t3, 40(sp)
    sw t4, 44(sp)
    sw t5, 48(sp)
    sw t6, 52(sp)
    fsw ft0, 56(sp)
    fsw ft1, 60(sp)
    fsw ft2, 64(sp)
    fsw ft3, 68(sp)
    fsw ft4, 72(sp)
    fsw ft5, 76(sp)
    fsw ft6, 80(sp)
    fsw ft7, 84(sp)
    fsw fa0, 88(sp)
    fsw fa1, 92(sp)
    fsw fa2, 96(sp)
    fsw fa3, 100(sp)
    fsw fa4, 104(sp)
    fsw fa5, 108(sp)
    fsw fa6, 112(sp)
    fsw fa7, 116(sp)
    fsw ft8, 120(sp)
    fsw ft9, 124(sp)
    fsw ft10, 128(sp)
    fsw ft11, 132(sp)
    frcsr t0
    sw t0, 136(sp)
    call glassly_input_observe
    lw t0, 136(sp)
    fscsr t0
    flw ft0, 56(sp)
    flw ft1, 60(sp)
    flw ft2, 64(sp)
    flw ft3, 68(sp)
    flw ft4, 72(sp)
    flw ft5, 76(sp)
    flw ft6, 80(sp)
    flw ft7, 84(sp)
    flw fa0, 88(sp)
    flw fa1, 92(sp)
    flw fa2, 96(sp)
    flw fa3, 100(sp)
    flw fa4, 104(sp)
    flw fa5, 108(sp)
    flw fa6, 112(sp)
    flw fa7, 116(sp)
    flw ft8, 120(sp)
    flw ft9, 124(sp)
    flw ft10, 128(sp)
    flw ft11, 132(sp)
    lw ra, 0(sp)
    lw a0, 4(sp)
    lw a1, 8(sp)
    lw a2, 12(sp)
    lw a3, 16(sp)
    lw a4, 20(sp)
    lw a5, 24(sp)
    lw a6, 28(sp)
    lw a7, 32(sp)
    lw t2, 36(sp)
    lw t3, 40(sp)
    lw t4, 44(sp)
    lw t5, 48(sp)
    lw t6, 52(sp)
    addi sp, sp, 144
    j .Lstock_display
#endif
.size display_gate, .-display_gate

#ifdef MM_WAKE_CONTROL
.section .text.wake_service_gate,"ax",@progbits
.align 1
.type wake_service_gate, @function
wake_service_gate:
#ifdef MM_SENSOR_CAPTURE
    li t0,0x76
    beq a0,t0,glassly_sensor_command
#endif
#ifdef MM_BLE_PROBE
    li t0,0x74
    beq a0,t0,glassly_ble_probe_command
#endif
#ifdef MM_MICROPHONE_CONTROL
    li t0, 0x77
    beq a0,t0,glassly_microphone_command
#endif
    li t0, 0x79
    beq a0, t0, .Lwake_command
#ifdef MM_NOTIFICATION_RELAY
    li t0, 0x78
    beq a0, t0, glassly_notification_command
#endif
    li t0, 0x042e4680
    jr t0
.Lwake_command:
    j glassly_wake_command
.size wake_service_gate, .-wake_service_gate
#endif
