
void FUN_ram_042ac430(undefined4 param_1)

{
  uint uVar1;
  int iVar2;
  undefined4 uVar3;
  undefined4 local_14;
  
  gp = &DAT_ram_02011688;
  local_14 = param_1;
  if (DAT_ram_02010314 == 0) {
    iVar2 = FUN_ram_02003d5e(0xe6,5);
    if (iVar2 != 0) {
      uVar3 = FUN_ram_042ac094();
      FUN_ram_02003d9c(0xe6,5,0x60002e90,1,uVar3);
    }
    FUN_ram_042ac3de(local_14);
  }
  else {
    while ((uVar1 = FUN_ram_0200f07e(DAT_ram_02010314), 1 < uVar1 ||
           (iVar2 = FUN_ram_0200ee8c(DAT_ram_02010314,&local_14), iVar2 == 0))) {
      FUN_ram_0200f758(1);
    }
  }
  return;
}

