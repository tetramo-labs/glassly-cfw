OUTPUT_ARCH(riscv)
ENTRY(service_entry)
MEMORY { extension (rx) : ORIGIN = 0x0439bea0, LENGTH = 0x18000 }
PHDRS { code PT_LOAD FLAGS(5); }
SECTIONS {
    .service_entry 0x0439bea0 : { KEEP(*(.text.service_entry)) } > extension :code
    .display_entry 0x0439bee0 : { KEEP(*(.text.display_entry)) } > extension
    .text : { *(.text .text.*) } > extension
    .rodata (READONLY) : { *(.rodata .rodata.* .srodata .srodata.*) BYTE(0); . = ALIGN(16); } > extension
    .data : { *(.data .data.* .sdata .sdata.* .tdata .tdata.*) } > extension
    .bss : { *(.bss .bss.* .sbss .sbss.* .tbss .tbss.* COMMON) } > extension
    .got : { *(.got .got.* .igot .igot.*) } > extension
    .initializers : { *(.init .fini .init_array* .fini_array* .ctors* .dtors*) } > extension
    /DISCARD/ : { *(.comment .note* .eh_frame* .riscv.attributes) }
    ASSERT(service_entry == 0x0439bea0, "Service entry differs from pinned profile")
    ASSERT(SIZEOF(.service_entry) <= 0x40, "Service gate overlaps display gate")
    ASSERT(display_gate == 0x0439bee0, "Display entry differs from pinned profile")
    ASSERT(SIZEOF(.data) == 0, "Appended runtime cannot initialize writable static data")
    ASSERT(SIZEOF(.bss) == 0, "Appended runtime cannot reserve BSS/TLS")
    ASSERT(SIZEOF(.got) == 0, "Appended runtime cannot use a GOT")
    ASSERT(SIZEOF(.initializers) == 0, "Appended runtime cannot require constructors")
}
