
void FUN_ram_04291d36(uint param_1,uint param_2,uint param_3,int param_4,int param_5,uint param_6)

{
  bool bVar1;
  int iVar2;
  undefined4 uVar3;
  int iVar4;
  int iVar5;
  uint uVar6;
  uint uVar7;
  uint uVar8;
  uint uVar9;
  uint uVar10;
  int iVar11;
  int iVar12;
  uint *puVar13;
  uint uVar14;
  undefined1 local_69;
  short local_68;
  undefined2 local_66;
  short local_64;
  undefined2 local_62;
  uint local_60 [11];
  
  gp = &DAT_ram_02011688;
  iVar2 = FUN_ram_042917ba();
  if (iVar2 == 0) {
    iVar2 = FUN_ram_02003d5e(0xe6,5);
    if (iVar2 == 0) {
      return;
    }
    uVar3 = FUN_ram_04291576();
    FUN_ram_02003d9c(0xe6,5,0x60002b14,5,uVar3,param_1,param_2,param_3,param_4);
    return;
  }
  uVar10 = param_3 >> 1;
  if ((param_5 != 0) && (param_6 < param_4 * uVar10)) {
    iVar2 = FUN_ram_02003d5e(0xe6,5);
    if (iVar2 == 0) {
      return;
    }
    uVar3 = FUN_ram_04291576();
    FUN_ram_02003fc2(0xe6,s__T_0x_08X__navi_app_c_1584___nav_ram_04365658,uVar3,param_4 * uVar10,
                     param_6);
    return;
  }
  uVar14 = (param_2 + param_4) - 1;
  if ((DAT_ram_02011e10 != 0) &&
     (((*(uint *)(DAT_ram_02011e10 + 0xec) >> 0x11 & 1) != 0 &&
      (*(int *)(DAT_ram_02011e10 + 0xa8) != 0)))) {
    uVar8 = (uint)*(ushort *)(DAT_ram_02011e10 + 0xac);
    if ((int)(uint)*(ushort *)(DAT_ram_02011e10 + 0xac) < (int)param_2) {
      uVar8 = param_2;
    }
    uVar7 = (uint)*(ushort *)(DAT_ram_02011e10 + 0xae);
    if ((int)(param_2 + param_4) <= (int)(uint)*(ushort *)(DAT_ram_02011e10 + 0xae)) {
      uVar7 = uVar14;
    }
    if ((int)uVar8 <= (int)uVar7) {
      iVar2 = (uVar8 - param_2) * uVar10 + param_5;
      do {
        iVar12 = (uVar8 - *(ushort *)(DAT_ram_02011e10 + 0xac)) * 300 + (param_1 >> 1) +
                 *(int *)(DAT_ram_02011e10 + 0xa8);
        if (param_5 == 0) {
          FUN_ram_020000da(iVar12,0,uVar10);
        }
        else {
          FUN_ram_02000000(iVar12,iVar2);
        }
        uVar8 = uVar8 + 1;
        iVar2 = iVar2 + uVar10;
      } while ((int)uVar8 <= (int)uVar7);
    }
  }
  iVar2 = 0;
  bVar1 = false;
  uVar7 = 0;
  uVar8 = 0xae;
  do {
    uVar9 = param_2;
    if ((int)param_2 < (int)uVar7) {
      uVar9 = uVar7;
    }
    if ((int)uVar14 < (int)uVar8) {
      uVar8 = uVar14;
    }
    if ((int)uVar9 <= (int)uVar8) {
      if ((((DAT_ram_02011e10 == 0) || ((*(byte *)(DAT_ram_02011e10 + 0xee) & 2) == 0)) ||
          (uVar7 = (uint)*(ushort *)(DAT_ram_02011e10 + 0xb2), (int)uVar7 < (int)uVar9)) ||
         (uVar6 = (uint)*(ushort *)(DAT_ram_02011e10 + 0xb0), (int)uVar8 < (int)uVar6)) {
        local_60[iVar2 * 2] = uVar9;
        local_60[iVar2 * 2 + 1] = uVar8;
      }
      else {
        if ((int)uVar9 < (int)uVar6) {
          local_60[iVar2 * 2] = uVar9;
          local_60[iVar2 * 2 + 1] = uVar6 - 1;
          iVar2 = iVar2 + 1;
        }
        if ((int)uVar8 <= (int)uVar7) goto LAB_ram_04291e9a;
        local_60[iVar2 * 2] = uVar7 + 1;
        local_60[iVar2 * 2 + 1] = uVar8;
      }
      iVar2 = iVar2 + 1;
    }
LAB_ram_04291e9a:
    uVar8 = 0x15d;
    uVar7 = 0xaf;
    if (bVar1) break;
    bVar1 = true;
  } while( true );
  puVar13 = local_60;
  iVar12 = 0;
  while( true ) {
    if (iVar12 == iVar2) {
      return;
    }
    uVar14 = *puVar13;
    uVar8 = puVar13[1];
    iVar4 = FUN_ram_0425f20e(uVar14 & 0xffff,uVar8 & 0xffff,0,&local_69);
    if (iVar4 == 0) break;
    iVar4 = FUN_ram_0425f7fa(param_1 & 0xffff,uVar14 & 0xffff,0);
    iVar11 = param_5 + (uVar14 - param_2) * uVar10;
    for (uVar7 = 0; uVar7 < (uVar8 - uVar14) + 1; uVar7 = uVar7 + 1) {
      iVar5 = uVar7 * 0x140 + iVar4;
      if (param_5 == 0) {
        FUN_ram_020000da(iVar5,0,uVar10);
      }
      else {
        FUN_ram_02000000(iVar5,iVar11);
      }
      iVar11 = iVar11 + uVar10;
    }
    iVar12 = iVar12 + 1;
    local_66 = (undefined2)uVar14;
    local_62 = (undefined2)uVar8;
    local_68 = (short)param_1;
    local_64 = (short)param_1 + (short)param_3 + -1;
    iVar4 = FUN_ram_0425f292(local_69,&local_68,iVar12 == iVar2);
    puVar13 = puVar13 + 2;
    if (iVar4 == 0) {
      uVar3 = 0x67c;
LAB_ram_04291ef0:
      FUN_ram_041fd196(s_navi_app_c_ram_0436564c,uVar3);
      return;
    }
  }
  uVar3 = 0x660;
  goto LAB_ram_04291ef0;
}

