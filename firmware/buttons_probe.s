.syntax unified
.cpu cortex-m0
.thumb
.text
// Sparse anchors: builders copy only audited hooks, pool count and tail.
.org 0x1918
    bl .Lcontrol
.org 0x1ae0
    bl .Lconnect
.org 0x3e28
    bl .Lpoll
.org 0x3e36
    bl .Lidle
.org 0x4874
.Lstock_connect:
.org 0x4a40
.Lstock_input:
.org 0x6d1c
.Lcapacity:
.org 0x6e50
.Lincrement_idle:
.org 0x764c
.Lgpio:
.org 0x82c8
.Lsubmit:
.org 0xb2b0
.Lclear_idle:
.org 0xbad0
.Lcancel_watchdog:
.org 0xbbba
    movs r2, #2            // Keep third 600-byte block out of OEM free list.

.org 0x11c04
.Lreset:
    ldr r1, .Lstate
    movs r0, #0
    str r0, [r1]
    str r0, [r1, #4]
    str r0, [r1, #8]
    bx lr
.Lconnect:
    push {r4,lr}
    mov r4, r0
    bl .Lreset
    mov r0, r4
    bl .Lstock_connect
    pop {r4,pc}
.Lcontrol:
    // Matched FF13 write. A1 starts a new session, A0 stops. Other values ignored.
    push {r4,lr}
    bl .Lclear_idle
    cmp r6, #3
    bne .Lcontrol_done
    ldr r4, [sp, #40]
    uxtb r4, r4
    cmp r4, #0xa0
    blo .Lcontrol_done
    cmp r4, #0xa1
    bhi .Lcontrol_done
    bl .Lreset
    subs r4, #0xa0
    strb r4, [r1, #8]
    movs r0, #2
    strb r0, [r1, #7]
.Lcontrol_done:
    pop {r4,pc}
.Lidle:
    push {r4,lr}
    ldr r0, .Lble
    ldrb r0, [r0]
    cmp r0, #2
    bne .Lidle_stock
    bl .Lclear_idle
    bl .Lcancel_watchdog
    pop {r4,pc}
.Lidle_stock:
    bl .Lincrement_idle
    pop {r4,pc}

.Lpoll:
    // Timer owner, ahead of OEM input congestion gates. 48-byte local frame.
    push {r4,r5,r6,r7,lr}
    sub sp, #28
    str r0, [sp, #24]
    ldr r4, .Lstate
    ldr r0, .Lble
    ldrb r0, [r0]
    cmp r0, #2
    beq .Lconnected
    bl .Lreset
    b .Ldone
.Lconnected:
    ldrb r0, [r4, #8]
    cmp r0, #0
    beq .Ldone
    bl .Lgpio
    // Whole-mask, two-consecutive-sample qualification; no millisecond claim.
    ldrh r1, [r4]
    strh r0, [r4]
    cmp r0, r1
    bne .Ltransmit
    ldrb r1, [r4, #10]
    cmp r1, #0
    beq .Lenqueue
    ldrh r1, [r4, #2]
    cmp r0, r1
    beq .Ltransmit
.Lenqueue:
    strh r0, [r4, #2]
    movs r1, #1
    strb r1, [r4, #10]
    ldrb r1, [r4, #4]
    ldrb r2, [r4, #5]
    cmp r2, #16
    blo .Lqueue_space
    movs r1, #0
    movs r2, #0
    strb r1, [r4, #4]
    ldrb r3, [r4, #7]
    movs r5, #1
    orrs r3, r5
    strb r3, [r4, #7]
.Lqueue_space:
    adds r1, r1, r2
    movs r3, #15
    ands r1, r3
    lsls r1, r1, #1
    adds r1, #12
    strh r0, [r4, r1]
    adds r2, #1
    strb r2, [r4, #5]
.Ltransmit:
    ldrb r0, [r4, #9]
    cmp r0, #0
    beq .Lnot_pending
    ldr r0, .Lack
    ldr r0, [r0]
    movs r1, #64
    tst r0, r1
    beq .Ldone             // Retain queue until command-09 zero-status ACK.
    movs r0, #0
    strb r0, [r4, #9]
    ldrb r0, [r4, #6]
    adds r0, #1
    strb r0, [r4, #6]
.Lnot_pending:
    ldrb r0, [r4, #5]
    cmp r0, #0
    beq .Ldone
    mrs r7, primask
    cpsid i
    ldr r0, .Lsleep
    ldrb r0, [r0]
    cmp r0, #0
    bne .Lrestore
    bl .Lcapacity
    cmp r0, #13            // IPC header 3 + handle 2 + packet 8; reserve one.
    bls .Lrestore
    ldr r0, .Ldescriptor
    str r0, [sp]
    add r0, sp, #8
    str r0, [sp, #4]
    ldr r0, .Lhandle
    ldrh r0, [r0]
    ldr r1, .Ltag
    orrs r0, r1
    str r0, [sp, #8]       // handle LE16, 47 04
    ldrh r0, [r4, #6]      // sequence, flags
    ldrb r1, [r4, #4]
    lsls r1, r1, #1
    adds r1, #12
    ldrh r1, [r4, r1]
    lsls r1, r1, #16
    orrs r0, r1
    str r0, [sp, #12]      // sequence, flags, mask LE16
    ldr r0, [sp, #12]
    str r0, [r4, #44]     // Retain in-flight sequence/flags/mask until ACK/reset.
    movs r0, #0
    str r0, [sp, #16]      // remaining two mask bytes are zero
    ldr r5, .Lack
    ldr r0, [r5]
    movs r1, #64
    bics r0, r1
    str r0, [r5]
    mov r0, sp
    bl .Lsubmit
    movs r0, #1
    strb r0, [r4, #9]
    ldrb r0, [r4, #4]
    adds r0, #1
    movs r1, #15
    ands r0, r1
    strb r0, [r4, #4]
    ldrb r0, [r4, #5]
    subs r0, #1
    strb r0, [r4, #5]
    movs r0, #0
    strb r0, [r4, #7]
.Lrestore:
    msr primask, r7
.Ldone:
    ldr r0, [sp, #24]
    bl .Lstock_input       // Preserve OEM reports and its return/idle policy.
    add sp, #28
    pop {r4,r5,r6,r7,pc}
.balign 4
.Lstate: .word 0x00022514
.Lble: .word 0x00020682
.Lack: .word 0x00020010
.Lsleep: .word 0x00020038
.Ldescriptor: .word 0x000a0900
.Lhandle: .word 0x00020648
.Ltag: .word 0x04470000
