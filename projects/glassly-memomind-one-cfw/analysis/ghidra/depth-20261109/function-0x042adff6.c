
void FUN_ram_042adff6(int param_1)

{
  uint uVar1;
  uint uVar2;
  uint uVar3;
  
  gp = &DAT_ram_02011688;
  uVar3 = (uint)DAT_ram_0201031c._1_1_;
  uVar1 = -((uint)(param_1 * 0x82) >> 3) - 0x7e;
  uVar2 = uVar1 & 0xff;
  if (uVar3 != uVar2) {
    DAT_ram_0201031c._1_1_ = (byte)uVar1;
    if (((byte)DAT_ram_02010318 & 2) == 0) {
      FUN_ram_042adc2a(0);
      uVar1 = uVar2;
      if (uVar2 < uVar3) {
        uVar1 = uVar3 + 0x15e;
        uVar3 = uVar2 + 0x15e;
      }
      FUN_ram_042ad780(uVar3,uVar1,10,3);
      FUN_ram_042adc2a(0);
      return;
    }
  }
  return;
}

