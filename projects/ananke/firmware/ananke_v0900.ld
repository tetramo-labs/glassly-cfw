ENTRY(ag_scan_hook)
SECTIONS {
    /* First byte after the complete OEM app, including its RAM initializer. */
    . = 0x01e52c38;
    .text : { *(.text*) *(.rodata*) }
    .data : { *(.data*) }
    .bss : { *(.bss*) *(COMMON) }
    /DISCARD/ : { *(.comment) *(.note*) *(.llvm_addrsig) }
}
/* One 128-byte page removed from the low end of the existing heap. The stock
 * zero-length secondary BSS loop is rebound to clear exactly this page. */
ag_state = 0x0000c280;
stock_connection = 0x00007920;
stock_keys = 0x000079e4;
/* The OEM calls this RAM routine through the 25-bit PC wrap. Give the linker
 * the equivalent forward alias so its signed 23-bit branch range check holds.
 * The emitted instruction is independently checked modulo 0x02000000. */
stock_scan = 0x020018c6;
stock_ccc_get = 0x01e169d8;
stock_ccc_set = 0x01e17178;
stock_ccc_clear = 0x01e1704e;
stock_att_queue = 0x01e16af4;
stock_bt_wake = 0x01e16678;
stock_critical_enter = 0x0200351c;
stock_critical_exit = 0x02003538;
