
undefined4 FUN_ram_04212eec(int param_1)

{
  undefined4 uVar1;
  undefined4 local_18;
  undefined2 local_14;
  
  gp = &DAT_ram_02011688;
  local_18 = DAT_ram_0201132c;
  local_14 = DAT_ram_02011330;
  if (param_1 == 0) {
    uVar1 = 1;
  }
  else {
    uVar1 = FUN_ram_04212ec0(param_1,&local_18);
  }
  return uVar1;
}

