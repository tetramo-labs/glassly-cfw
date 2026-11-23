
undefined4 FUN_ram_042ac4be(uint param_1)

{
  int iVar1;
  undefined4 uVar2;
  undefined4 uVar3;
  uint uVar4;
  undefined1 *puVar5;
  uint uVar6;
  uint uVar7;
  
  gp = &DAT_ram_02011688;
  if ((param_1 == 0) || ((param_1 & 0xfffffff8) != 0)) {
    iVar1 = FUN_ram_02003d5e(0xe6,5);
    uVar3 = 0;
    if (iVar1 != 0) {
      uVar2 = FUN_ram_042ac094();
      FUN_ram_02003fc2(0xe6,s__T_0x_08X__jbd013_hw_c_454___jbd_ram_043840d4,uVar2,param_1);
    }
  }
  else {
    puVar5 = &DAT_ram_020102f4;
    uVar6 = 0;
    uVar4 = 0;
    do {
      uVar7 = 1 << (uVar4 & 0x1f);
      if ((uVar7 & param_1) != 0) {
        if ((*(int *)(puVar5 + 0x14) == 0) ||
           (iVar1 = FUN_ram_0200ed78(*(int *)(puVar5 + 0x14),0xffffffff), iVar1 == 0)) {
          iVar1 = FUN_ram_02003d5e(0xe6,5);
          if (iVar1 != 0) {
            uVar3 = FUN_ram_042ac094();
            FUN_ram_02003fc2(0xe6,s__T_0x_08X__jbd013_hw_c_467___jbd_ram_04384120,uVar3,uVar7);
          }
          FUN_ram_042ac360(uVar6);
          gp = &DAT_ram_02011688;
          return 0;
        }
        uVar6 = uVar7 & 0xff | uVar6;
      }
      uVar4 = uVar4 + 1;
      puVar5 = puVar5 + 4;
    } while (uVar4 != 3);
    uVar3 = 1;
  }
  return uVar3;
}

