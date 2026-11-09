
void FUN_ram_042acca0(ushort *param_1,short *param_2,int param_3)

{
  short sVar1;
  int iVar2;
  int iVar3;
  ushort uVar4;
  
  gp = &DAT_ram_02011688;
  iVar2 = (param_3 + (uint)*param_1) * 0x10000;
  iVar3 = iVar2 >> 0x10;
  sVar1 = (short)(param_3 + (uint)*param_1);
  if (iVar3 < 0) {
    uVar4 = sVar1 + 0x280;
    *param_2 = *param_2 + -1;
  }
  else {
    if (iVar3 < 0x280) {
      *param_1 = (ushort)((uint)iVar2 >> 0x10);
      goto LAB_ram_042acccc;
    }
    uVar4 = sVar1 - 0x280;
    *param_2 = *param_2 + 1;
  }
  *param_1 = uVar4;
LAB_ram_042acccc:
  if (*param_2 < 0) {
    *param_2 = 0;
  }
  else if (0x1df < *param_2) {
    *param_2 = 0x1df;
  }
  if ((short)*param_1 < 0) {
    *param_1 = 0;
  }
  else if (0x27f < (short)*param_1) {
    *param_1 = 0x27f;
  }
  return;
}

