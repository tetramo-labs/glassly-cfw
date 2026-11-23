/* Preserve the stock call's arguments, return address and stack exactly.
 * t0 is caller-saved under the demonstrated RISC-V integer ABI.
 */
.section .text.entry,"ax",@progbits
.align 1
.global glassly_handler
.type glassly_handler, @function
glassly_handler:
    li t0, 0x7e
    beq a0, t0, glassly_probe
    li t0, 0x042e4680
    jr t0
.size glassly_handler, .-glassly_handler
