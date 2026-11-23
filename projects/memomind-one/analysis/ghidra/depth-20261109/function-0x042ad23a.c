
int FUN_ram_042ad23a(undefined4 param_1,undefined4 param_2,int param_3,uint param_4)

{
  int iVar1;
  int local_24 [3];
  
  gp = &DAT_ram_02011688;
  param_4 = DAT_ram_02010318 >> 4 & 3 & param_4;
  if (param_4 == 0) {
    local_24[0] = 0;
  }
  else {
    local_24[0] = 0;
    if (param_3 != 0) {
      local_24[0] = FUN_ram_042ac604(param_4,0,5,1,param_4,0);
      FUN_ram_042acc74(param_1,param_2,*(undefined4 *)(local_24[0] + 0x18));
      iVar1 = FUN_ram_042ac604(param_4,0,param_3,1,0,0);
      FUN_ram_020000da(*(undefined4 *)(iVar1 + 0x18),0,param_3);
      FUN_ram_042ad21a(local_24,iVar1);
    }
  }
  return local_24[0];
}

