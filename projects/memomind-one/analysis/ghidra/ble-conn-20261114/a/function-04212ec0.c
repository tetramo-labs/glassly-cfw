
bool FUN_ram_04212ec0(int param_1,int param_2)

{
  int iVar1;
  
  gp = &DAT_ram_02011688;
  if ((param_1 == 0) || (param_2 == 0)) {
    return false;
  }
  iVar1 = FUN_ram_0200b400(param_1,param_2,6);
  return iVar1 == 0;
}

