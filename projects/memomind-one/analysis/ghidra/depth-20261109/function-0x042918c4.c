
uint FUN_ram_042918c4(uint param_1,uint param_2)

{
  bool bVar1;
  uint uVar2;
  int iVar3;
  int iVar4;
  uint uVar5;
  uint uVar6;
  uint uVar7;
  uint uVar8;
  uint uVar9;
  undefined1 local_49;
  undefined2 local_48;
  undefined2 local_46;
  undefined2 local_44;
  undefined2 local_42;
  
  gp = &DAT_ram_02011688;
  if (DAT_ram_02011e10 != 0) {
    uVar2 = *(uint *)(DAT_ram_02011e10 + 0xec) >> 0x11 & 1;
    if (uVar2 == 0) {
      gp = &DAT_ram_02011688;
      return 0;
    }
    if ((((*(int *)(DAT_ram_02011e10 + 0xa8) != 0) && (param_1 <= param_2)) &&
        (*(ushort *)(DAT_ram_02011e10 + 0xac) <= param_1)) &&
       (param_2 <= *(ushort *)(DAT_ram_02011e10 + 0xae))) {
      bVar1 = false;
      uVar5 = 0;
      uVar6 = 0xae;
      do {
        uVar7 = param_1;
        if (param_1 < uVar5) {
          uVar7 = uVar5;
        }
        uVar8 = uVar7 & 0xffff;
        uVar5 = param_2;
        if (uVar6 < param_2) {
          uVar5 = uVar6;
        }
        uVar6 = uVar5 & 0xffff;
        if (uVar8 <= uVar6) {
          iVar3 = FUN_ram_0425f20e(uVar8,uVar6,0,&local_49);
          if (iVar3 == 0) {
            return 0;
          }
          iVar4 = FUN_ram_0425f7fa(0,uVar8,0);
          iVar3 = *(int *)(DAT_ram_02011e10 + 0xa8) +
                  (uVar8 - *(ushort *)(DAT_ram_02011e10 + 0xac)) * 300;
          for (uVar9 = 0; uVar9 < (uVar6 - uVar8) + 1; uVar9 = uVar9 + 1) {
            FUN_ram_02000000(uVar9 * 0x140 + iVar4,iVar3,300);
            iVar3 = iVar3 + 300;
          }
          local_48 = 0;
          local_46 = (undefined2)uVar7;
          local_44 = 599;
          local_42 = (undefined2)uVar5;
          iVar3 = FUN_ram_0425f292(local_49,&local_48,1);
          if (iVar3 == 0) {
            FUN_ram_041fd196(s_navi_app_c_ram_0436564c,0x567);
            return 0;
          }
        }
        if (bVar1) {
          gp = &DAT_ram_02011688;
          return uVar2;
        }
        bVar1 = true;
        uVar5 = 0xaf;
        uVar6 = 0x15d;
      } while( true );
    }
  }
  return 0;
}

