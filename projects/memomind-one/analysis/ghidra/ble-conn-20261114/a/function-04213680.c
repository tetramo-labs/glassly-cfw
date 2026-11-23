
undefined1 * FUN_ram_04213680(undefined4 param_1)

{
  int iVar1;
  int iVar2;
  undefined4 uVar3;
  undefined4 uVar4;
  undefined1 *puVar5;
  
  gp = &DAT_ram_02011688;
  iVar1 = FUN_ram_04212eec();
  if (iVar1 == 0) {
    iVar1 = 0;
    do {
      puVar5 = &DAT_ram_020128c4;
      iVar2 = FUN_ram_04212ec0(&DAT_ram_020128c5 + iVar1,param_1);
      if (iVar2 != 0) {
        return &DAT_ram_020128c4 + iVar1;
      }
      iVar1 = iVar1 + 0x24;
    } while (iVar1 != 0x6c);
    iVar1 = FUN_ram_04235dd0();
    iVar2 = 0;
    if (iVar1 != 0) {
      while ((1 < (byte)puVar5[7] || (2 < (byte)puVar5[0x14]))) {
        iVar2 = iVar2 + 1;
        puVar5 = puVar5 + 0x24;
        if (iVar2 == 3) {
          return (undefined1 *)0x0;
        }
      }
      iVar1 = iVar2 * 0x24;
      (&DAT_ram_020128c4)[iVar1] = (char)iVar2;
      FUN_ram_0200b23e(&DAT_ram_020128c5 + iVar1,6,param_1,6);
      *(undefined4 *)(&DAT_ram_020128cc + iVar1) = 0x10101;
      (&DAT_ram_020128cb)[iVar1] = 1;
      *(undefined4 *)(&DAT_ram_020128d0 + iVar1) = 0;
      *(undefined4 *)(&DAT_ram_020128d4 + iVar1) = 0xff0000;
      *(undefined2 *)(&DAT_ram_020128d8 + iVar1) = 1;
      FUN_ram_0200b27e(&DAT_ram_020128da + iVar1,6,0,6);
      return &DAT_ram_020128c4 + iVar1;
    }
    uVar4 = 0x60000954;
    uVar3 = 4;
  }
  else {
    uVar4 = 0x60000950;
    uVar3 = 5;
  }
  FUN_ram_02003d9c(0xe0,uVar3,uVar4,0);
  return (undefined1 *)0x0;
}

