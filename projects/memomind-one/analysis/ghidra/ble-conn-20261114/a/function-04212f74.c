
undefined4 FUN_ram_04212f74(int param_1)

{
  int iVar1;
  undefined4 local_18;
  undefined2 local_14;
  
  gp = &DAT_ram_02011688;
  local_18 = DAT_ram_0201132c;
  local_14 = DAT_ram_02011330;
  iVar1 = FUN_ram_04223cba();
  if (iVar1 == 0) {
    FUN_ram_042dc168(&local_18);
    iVar1 = FUN_ram_04212eec(&local_18);
    if ((iVar1 == 0) &&
       ((iVar1 = FUN_ram_04223eae(&local_18), iVar1 == 1 ||
        ((iVar1 != 2 && (iVar1 = FUN_ram_042339c2(&local_18), iVar1 != 0)))))) {
      if (param_1 != 0) {
        FUN_ram_0200b23e(param_1,6,&local_18,6);
      }
      return 1;
    }
  }
  return 0;
}

