
uint FUN_ram_042133e2(undefined4 param_1)

{
  uint uVar1;
  
  gp = &DAT_ram_02011688;
  if (DAT_ram_020128bc == '\0') {
    return 0;
  }
  uVar1 = FUN_ram_04212ec0(&DAT_ram_020128b6,param_1);
  return uVar1 & 1;
}

