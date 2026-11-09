
undefined1 FUN_ram_042ae116(void)

{
  undefined1 *puVar1;
  int iVar2;
  
  gp = &DAT_ram_02011688;
  puVar1 = &DAT_ram_04384f90;
  iVar2 = 0;
  do {
    if ((uint)(byte)puVar1[1] == (DAT_ram_0201031c & 0x3f)) {
      gp = &DAT_ram_02011688;
      return (&DAT_ram_04384f90)[iVar2 * 2];
    }
    iVar2 = iVar2 + 1;
    puVar1 = puVar1 + 2;
  } while (iVar2 != 9);
  return 0;
}

