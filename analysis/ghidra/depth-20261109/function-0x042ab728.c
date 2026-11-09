
void FUN_ram_042ab728(uint *param_1,int param_2,int param_3,int param_4)

{
  byte bVar1;
  byte bVar2;
  byte *pbVar3;
  byte *pbVar4;
  byte *pbVar5;
  uint uVar6;
  int iVar7;
  byte *pbVar8;
  byte *pbVar9;
  byte *pbVar10;
  uint uVar11;
  uint uVar12;
  int iVar13;
  
  gp = &DAT_ram_02011688;
  uVar11 = param_1[1];
  uVar12 = param_1[3];
  if ((param_4 == 0) && (DAT_ram_02011e88 != '\0')) {
    if ((int)uVar11 < (int)(uint)DAT_ram_02011e8a) {
      uVar11 = (uint)DAT_ram_02011e8a;
    }
    if ((int)(uint)DAT_ram_02011e8c < (int)uVar12) {
      uVar12 = (uint)DAT_ram_02011e8c;
    }
    if ((int)uVar12 < (int)uVar11) {
      gp = &DAT_ram_02011688;
      return;
    }
  }
  pbVar4 = (byte *)FUN_ram_0425f7fa((short)*param_1,uVar11 & 0xffff,param_4);
  pbVar5 = (byte *)(param_2 + (uVar11 - param_1[1]) * param_3);
  for (; (int)uVar11 <= (int)uVar12; uVar11 = uVar11 + 1) {
    uVar6 = *param_1;
    if ((uVar6 & 1) == 0) {
      pbVar8 = pbVar5;
      pbVar9 = pbVar4;
    }
    else {
      uVar6 = uVar6 + 1;
      *pbVar4 = *pbVar4 & 0xf0 | *pbVar5 >> 4;
      pbVar8 = pbVar5 + 1;
      pbVar9 = pbVar4 + 1;
    }
    uVar6 = (param_1[2] - uVar6) + 1;
    iVar7 = (int)uVar6 >> 2;
    pbVar10 = pbVar9;
    for (iVar13 = 0; pbVar3 = pbVar8 + iVar13 * 4, iVar13 < iVar7; iVar13 = iVar13 + 1) {
      bVar1 = pbVar3[2];
      bVar2 = pbVar3[3];
      *pbVar10 = pbVar3[1] >> 4 | (&DAT_ram_043840b8)[*pbVar3 >> 4];
      pbVar10[1] = bVar2 >> 4 | (&DAT_ram_043840b8)[bVar1 >> 4];
      pbVar10 = pbVar10 + 2;
    }
    if (iVar7 < 0) {
      iVar7 = 0;
    }
    pbVar9 = pbVar9 + iVar7 * 2;
    pbVar8 = pbVar8 + iVar7 * 4;
    pbVar10 = pbVar9;
    if ((uVar6 & 2) != 0) {
      bVar1 = *pbVar8;
      pbVar3 = pbVar8 + 1;
      pbVar10 = pbVar9 + 1;
      pbVar8 = pbVar8 + 2;
      *pbVar9 = *pbVar3 >> 4 | (&DAT_ram_043840b8)[bVar1 >> 4];
    }
    if ((param_1[2] & 1) == 0) {
      *pbVar10 = (&DAT_ram_043840b8)[*pbVar8 >> 4] | *pbVar10 & 0xf;
    }
    pbVar5 = pbVar5 + param_3;
    pbVar4 = pbVar4 + 0x140;
  }
  return;
}

