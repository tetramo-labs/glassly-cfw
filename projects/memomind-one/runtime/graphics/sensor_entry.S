.option norelax
.macro acquire mask
    mv t0,sp
    andi sp,sp,-16
    addi sp,sp,-32
    sw t0,0(sp)
    sw ra,4(sp)
    sw a0,8(sp)
    sw a1,12(sp)
    sw a2,16(sp)
    li a0,\mask
    call glassly_sensor_begin
    sw a0,20(sp)
    lw a0,8(sp)
    lw a1,12(sp)
    lw a2,16(sp)
.endm
.macro finish mask,pointer,success
    sw a0,24(sp)
    li t0,\success
    bne a0,t0,1f
    li a0,\mask
    lw a1,20(sp)
    lw a2,\pointer(sp)
    call glassly_sensor_finish
1:
    lw a0,24(sp)
    lw ra,4(sp)
    lw t0,0(sp)
    mv sp,t0
    ret
.endm
.section .text.glassly_sensor_imu_entry,"ax",@progbits
.align 1
.global glassly_sensor_imu_entry
.type glassly_sensor_imu_entry,@function
glassly_sensor_imu_entry:
    acquire 1
    li t0,0x0434742e
    jalr ra,t0,0
    finish 1,12,0
.size glassly_sensor_imu_entry,.-glassly_sensor_imu_entry
.section .text.glassly_sensor_als_entry,"ax",@progbits
.align 1
.global glassly_sensor_als_entry
.type glassly_sensor_als_entry,@function
glassly_sensor_als_entry:
    acquire 2
    call glassly_sensor_als_original
    finish 2,8,1
.size glassly_sensor_als_entry,.-glassly_sensor_als_entry
.type glassly_sensor_als_original,@function
glassly_sensor_als_original:
    .byte 0x79,0x71,0x22,0xd4,0x4a,0xd0,0x4e,0xce
    li t0,0x0422b682
    jr t0
.size glassly_sensor_als_original,.-glassly_sensor_als_original
