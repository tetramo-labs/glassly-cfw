
void FUN_ram_042ae916(float param_1)

{
  float fVar1;
  float fVar2;
  int iVar3;
  int iVar4;
  
  gp = &DAT_ram_02011688;
  if ((DAT_ram_02010318 >> 2 & 1) == 0) {
    FUN_ram_042ae81c();
    DAT_ram_02010318 = DAT_ram_02010318 | 4;
  }
  if (param_1 < 0.0) {
    param_1 = 0.0;
  }
  else if (DAT_ram_0201110c < param_1) {
    param_1 = DAT_ram_0201110c;
  }
  iVar4 = (int)param_1;
  iVar3 = iVar4;
  if (iVar4 < 10) {
    iVar3 = iVar4 + 1;
  }
  fVar1 = (float)*(ushort *)((int)&DAT_ram_02010318 + (iVar4 + 8) * 2);
  fVar1 = ((float)*(ushort *)((int)&DAT_ram_02010318 + (iVar3 + 8) * 2) - fVar1) *
          (param_1 - (float)iVar4) + fVar1;
  fVar2 = (float)*(ushort *)((int)&DAT_ram_0201031c + (iVar4 + 0x10) * 2 + 2);
  fVar2 = ((float)*(ushort *)((int)&DAT_ram_0201031c + (iVar3 + 0x10) * 2 + 2) - fVar2) *
          (param_1 - (float)iVar4) + fVar2;
  FUN_ram_042acdb0((uint)(-1 < (int)fVar1) * (int)fVar1 & 0xffff,
                   (uint)(-1 < (int)fVar2) * (int)fVar2 & 0xffff,3);
  return;
}

