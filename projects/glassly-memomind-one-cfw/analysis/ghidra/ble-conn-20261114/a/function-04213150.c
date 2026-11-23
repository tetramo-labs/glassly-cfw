
void FUN_ram_04213150(undefined1 param_1,undefined4 param_2,undefined1 param_3,undefined1 param_4,
                     undefined1 param_5)

{
  int iVar1;
  
  gp = &DAT_ram_02011688;
  if (DAT_ram_020128bc != '\0') {
    iVar1 = FUN_ram_04212eec(param_2);
    if (iVar1 == 0) {
      FUN_ram_0200b23e(&DAT_ram_020128b6,6,param_2,6);
    }
    DAT_ram_020128bd = param_1;
    DAT_ram_020128be = param_3;
    DAT_ram_020128bf = param_4;
    DAT_ram_020128c0 = param_5;
    FUN_ram_04236404(0,0x3f4);
    iVar1 = FUN_ram_042363f4(0,0x3f4,0,0,300000);
    if (iVar1 != 0) {
      DAT_ram_020128be = (undefined1)iVar1;
      DAT_ram_020128bd = 10;
      FUN_ram_02003d9c(0xe0,4,0x6000093c,1,iVar1);
      FUN_ram_04212ff0();
      return;
    }
  }
  return;
}

