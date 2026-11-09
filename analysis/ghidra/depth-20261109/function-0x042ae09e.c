
void FUN_ram_042ae09e(uint param_1)

{
  byte *pbVar1;
  uint uVar2;
  uint uVar3;
  int iVar4;
  
  gp = &DAT_ram_02011688;
  pbVar1 = &DAT_ram_04384f90;
  iVar4 = 0;
  do {
    if (*pbVar1 == param_1) {
      uVar2 = (uint)(byte)(&DAT_ram_04384f91)[iVar4 * 2];
      goto LAB_ram_042ae0be;
    }
    iVar4 = iVar4 + 1;
    pbVar1 = pbVar1 + 2;
  } while (iVar4 != 9);
  uVar2 = 0;
LAB_ram_042ae0be:
  uVar3 = DAT_ram_0201031c;
  if ((DAT_ram_0201031c & 0x3f) != uVar2) {
    uVar3 = DAT_ram_0201031c & 0xffffffc0 | uVar2 & 0x3f;
    if (((byte)DAT_ram_02010318 & 2) == 0) {
      uVar2 = DAT_ram_0201031c >> 8 & 0xff;
      DAT_ram_0201031c = uVar3;
      FUN_ram_042ad780(uVar2,uVar2 + 1,1,3);
      FUN_ram_042adc2a(0);
      return;
    }
  }
  DAT_ram_0201031c = uVar3;
  return;
}

