OUTPUT_ARCH(riscv)
ENTRY(glassly_handler)
MEMORY {
    extension (rx) : ORIGIN = 0x0439bea0, LENGTH = 0x4f160
}
SECTIONS {
    .text : { KEEP(*(.text.entry)) *(.text .text.*) } > extension
    .rodata : { *(.rodata .rodata.*) . = ALIGN(16); } > extension
    .data : { *(.data .data.* .sdata .sdata.* .got .got.*) } > extension
    .bss : { *(.bss .bss.* .sbss .sbss.* COMMON) } > extension
    /DISCARD/ : { *(.comment .note* .eh_frame* .riscv.attributes) }
    ASSERT(glassly_handler == 0x0439bea0, "Entry differs from pinned hook profile")
    ASSERT(SIZEOF(.data) == 0, "Diagnostic runtime must have no initialized writable data")
    ASSERT(SIZEOF(.bss) == 0, "Diagnostic runtime must have no BSS")
}
