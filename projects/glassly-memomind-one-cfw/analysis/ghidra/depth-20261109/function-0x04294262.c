
undefined4 FUN_ram_04294262(uint param_1,uint param_2)

{
  byte bVar1;
  bool bVar2;
  uint uVar3;
  undefined **ppuVar4;
  int iVar5;
  undefined4 uVar6;
  uint uVar7;
  uint uVar8;
  uint uVar9;
  int iVar10;
  uint uVar11;
  int iVar12;
  undefined1 local_41 [13];
  
  gp = &DAT_ram_02011688;
  if (((((DAT_ram_02011e10 != 0) && (DAT_ram_020100ac != '\0')) &&
       (ppuVar4 = (undefined **)FUN_ram_0425db22(), ppuVar4 == &PTR_DAT_ram_043656cc_ram_02010078))
      && (((*(uint *)(DAT_ram_02011e10 + 0xec) & 0x8020) == 0 && (param_1 <= param_2)))) &&
     (param_1 < 0x15e)) {
    if (0x15d < param_2) {
      param_2 = 0x15d;
    }
    uVar11 = param_2 & 0xffff;
    if ((*(byte *)(DAT_ram_02011e10 + 0xee) & 2) == 0) {
      uVar3 = param_1;
    }
    else {
      uVar3 = (uint)*(ushort *)(DAT_ram_02011e10 + 0xac);
      if (param_1 < *(ushort *)(DAT_ram_02011e10 + 0xac)) {
        uVar3 = param_1;
      }
      uVar8 = (uint)*(ushort *)(DAT_ram_02011e10 + 0xae);
      if (*(ushort *)(DAT_ram_02011e10 + 0xae) < uVar11) {
        uVar8 = uVar11;
      }
      uVar11 = uVar8;
      uVar3 = uVar3 & 0xffff;
    }
    iVar12 = ((uVar11 - uVar3) + 1) * 300;
    iVar5 = FUN_ram_0434e6da(iVar12);
    if (iVar5 == 0) {
      iVar5 = FUN_ram_02003d5e(0xe6,4);
      if (iVar5 != 0) {
        uVar6 = FUN_ram_04291576();
        FUN_ram_02003d9c(0xe6,4,0x60002b58,2,uVar6,iVar12);
      }
    }
    else {
      bVar2 = false;
      uVar9 = 0;
      uVar8 = 0xae;
      while( true ) {
        uVar7 = uVar3 & 0xffff;
        if (uVar3 < uVar9) {
          uVar7 = uVar9;
        }
        uVar9 = uVar11;
        if (uVar8 < uVar11) {
          uVar9 = uVar8;
        }
        if (uVar7 <= uVar9) break;
LAB_ram_042943b4:
        uVar8 = 0x15d;
        uVar9 = 0xaf;
        if (bVar2) {
          if (((*(byte *)(DAT_ram_02011e10 + 0xee) & 2) != 0) &&
             (*(int *)(DAT_ram_02011e10 + 0xa8) != 0)) {
            uVar9 = (uint)*(ushort *)(DAT_ram_02011e10 + 0xac);
            uVar8 = uVar9;
            if (uVar9 < *(ushort *)(DAT_ram_02011e10 + 0xb0)) {
              uVar8 = (uint)*(ushort *)(DAT_ram_02011e10 + 0xb0);
            }
            uVar7 = (uint)*(ushort *)(DAT_ram_02011e10 + 0xae);
            if ((uint)*(ushort *)(DAT_ram_02011e10 + 0xb2) <
                (uint)*(ushort *)(DAT_ram_02011e10 + 0xae)) {
              uVar7 = (uint)*(ushort *)(DAT_ram_02011e10 + 0xb2);
            }
            if (uVar8 <= uVar7) {
              FUN_ram_02000000((uVar8 - uVar3) * 300 + iVar5,
                               *(int *)(DAT_ram_02011e10 + 0xa8) + (uVar8 - uVar9) * 300,
                               ((uVar7 - uVar8) + 1) * 300);
            }
          }
          FUN_ram_0434e6ee(*(undefined4 *)(DAT_ram_02011e10 + 0xa8));
          iVar12 = DAT_ram_02011e10;
          bVar1 = *(byte *)(DAT_ram_02011e10 + 0xee);
          *(int *)(DAT_ram_02011e10 + 0xa8) = iVar5;
          *(short *)(iVar12 + 0xac) = (short)uVar3;
          *(short *)(iVar12 + 0xae) = (short)uVar11;
          *(short *)(iVar12 + 0xb0) = (short)param_1;
          *(short *)(iVar12 + 0xb2) = (short)param_2;
          *(byte *)(iVar12 + 0xee) = bVar1 | 2;
          FUN_ram_042abedc(1,uVar3,uVar11);
          gp = &DAT_ram_02011688;
          return 1;
        }
        bVar2 = true;
      }
      iVar12 = FUN_ram_0425f20e(uVar7,uVar9,0,local_41);
      if (iVar12 != 0) {
        iVar12 = FUN_ram_0425f7fa(0,uVar7,0);
        iVar10 = (uVar7 - uVar3) * 300 + iVar5;
        for (uVar8 = 0; uVar8 < (uVar9 - uVar7) + 1; uVar8 = uVar8 + 1) {
          FUN_ram_02000000(iVar10,uVar8 * 0x140 + iVar12,300);
          iVar10 = iVar10 + 300;
        }
        iVar12 = FUN_ram_0425f292(local_41[0],0,1);
        if (iVar12 != 0) goto LAB_ram_042943b4;
        FUN_ram_041fd196(s_navi_app_c_ram_0436564c,0x535);
      }
      iVar12 = FUN_ram_02003d5e(0xe6,4);
      if (iVar12 != 0) {
        uVar6 = FUN_ram_04291576();
        FUN_ram_02003d9c(0xe6,4,0x60002b5c,1,uVar6);
      }
      FUN_ram_0434e6ee(iVar5);
    }
  }
  return 0;
}

