.syntax unified
.cpu cortex-m0
.thumb
.text
// Section-relative anchors let the assembler resolve all BL instructions.
// Only the two hook words and [0x11c04, end) are copied into the image.
.org 0x1918
    bl .Lecho
.org 0x3e36
    bl .Lidle
.org 0x6d1c
.Lcapacity:
.org 0x6e50
.Lincrement_idle:
.org 0x82c8
.Lsubmit:
.org 0xb2b0
.Lclear_idle:
.org 0xbad0
.Lcancel_watchdog:

.org 0x11c04
.Lecho:
    // Replaces the existing clear-idle call in the matched FF13 write path.
    // Caller r5 = matched dynamic handle; r6 = handle+value length.
    // Caller [sp+32] begins characteristic value. Preserve all saved registers.
    push {r4,r5,r6,r7,lr}
    sub sp, #28
    bl .Lclear_idle
    cmp r6, #3
    bne .Lecho_return
    ldr r0, [sp, #80]       // old sp+32; only the first byte is used
    uxtb r0, r0
    lsls r0, r0, #16
    orrs r0, r5
    str r0, [sp, #8]        // LE16 dynamic handle, one echo byte, padding
    ldr r0, .Ldescriptor
    str r0, [sp]            // type 0 (stock sets 1), opcode 09, length 3
    add r0, sp, #8
    str r0, [sp, #4]
    mrs r4, primask
    cpsid i
    ldr r0, .Lsleep_flag
    ldrb r0, [r0]
    cmp r0, #0
    bne .Lrestore_irq       // do not enter stock's delayed wake path
    bl .Lcapacity
    cmp r0, #6             // 3-byte IPC header + 3-byte payload
    bls .Lrestore_irq       // retain one byte: exact fill is ambiguous
    mov r0, sp
    bl .Lsubmit            // synchronous copy, no wait/retry/ACK claim
.Lrestore_irq:
    msr primask, r4
.Lecho_return:
    add sp, #28
    pop {r4,r5,r6,r7,pc}
.balign 4
.Ldescriptor: .word 0x00030900
.Lsleep_flag: .word 0x00020038

.org 0x11cc0
.Lidle:
    // Experimental policy: any BLE connection keeps the controller awake,
    // regardless of CCC state. Disconnected operation retains stock counting.
    push {r4,lr}
    ldr r0, .Lble_state
    ldrb r0, [r0]
    cmp r0, #2
    bne .Lstock_idle
    bl .Lclear_idle
    bl .Lcancel_watchdog
    pop {r4,pc}
.Lstock_idle:
    bl .Lincrement_idle
    pop {r4,pc}
.balign 4
.Lble_state: .word 0x00020682
