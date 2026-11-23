
void FUN_ram_042ae172(uint param_1)

{
  uint uVar1;
  int iVar2;
  
  gp = &DAT_ram_02011688;
  iVar2 = FUN_ram_0424417a();
  if (iVar2 != 0) {
    uVar1 = DAT_ram_02010318 >> 4 & 3;
    if (param_1 != uVar1) {
      if ((DAT_ram_02010318 & 2) == 0) {
        if ((~param_1 & uVar1) != 0) {
          FUN_ram_042ad850(0);
        }
        if (param_1 == 0) {
          FUN_ram_042acefc(0);
        }
        DAT_ram_02010318 =
             CONCAT31(DAT_ram_02010318._1_3_,
                      (byte)DAT_ram_02010318 & 0xcf | (byte)((param_1 & 3) << 4));
        if ((~uVar1 & param_1) != 0) {
          if (uVar1 == 0) {
            FUN_ram_042acefc(1);
          }
          FUN_ram_042ad850(1,~uVar1 & param_1);
          FUN_ram_042adc2a(0);
          return;
        }
      }
      else {
        DAT_ram_02010318 =
             CONCAT31(DAT_ram_02010318._1_3_,
                      (byte)DAT_ram_02010318 & 0xcf | (byte)((param_1 & 3) << 4));
      }
    }
  }
  return;
}

