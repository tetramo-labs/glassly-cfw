
void FUN_ram_042abb04(undefined4 param_1,int *param_2,int param_3)

{
  bool bVar1;
  byte bVar2;
  int iVar3;
  undefined4 uVar4;
  int iVar5;
  uint uVar6;
  uint uVar7;
  int iVar8;
  undefined4 *puVar9;
  int iVar10;
  char local_41;
  undefined1 auStack_40 [4];
  int local_3c;
  int local_34;
  
  gp = &DAT_ram_02011688;
  if (DAT_ram_0201165d != '\0') {
    FUN_ram_042d02c6();
    uVar6 = param_2[1];
    iVar5 = (param_2[2] - *param_2) + 1;
    if (((((int)uVar6 < 0xaf) && (uVar7 = param_2[3], 0xae < (int)uVar7)) &&
        ((int)(uVar7 - uVar6) < 0x10)) &&
       ((iVar3 = FUN_ram_042ab892(&DAT_ram_0202daa0), iVar3 == 0 &&
        (iVar3 = FUN_ram_042ab892(&DAT_ram_0202dab0), iVar3 == 0)))) {
      iVar3 = FUN_ram_0425f20e(uVar6 & 0xffff,uVar7 & 0xffff,0,&local_41);
      if (iVar3 == 0) {
        FUN_ram_041fd196(s_lv_port_disp_c_ram_043840a8,0x2cd);
      }
      else {
        if (local_41 != '\x03') {
          FUN_ram_041fd196(s_lv_port_disp_c_ram_043840a8,0x2d1);
        }
        FUN_ram_042ab728(param_2,param_3,iVar5,0);
        FUN_ram_02000000(auStack_40,param_2,0x10);
        uVar4 = FUN_ram_042d025e(param_1);
        FUN_ram_042d02c6();
        FUN_ram_042ab93e(auStack_40,local_41,uVar4);
      }
    }
    else {
      puVar9 = &DAT_ram_0202daa0;
      iVar8 = 0;
      iVar10 = 0;
      iVar3 = 0xae;
      while( true ) {
        FUN_ram_02000000(auStack_40,param_2,0x10);
        if (local_3c < iVar10) {
          local_3c = iVar10;
        }
        if (iVar3 < local_34) {
          local_34 = iVar3;
        }
        if (local_3c <= local_34) {
          iVar10 = FUN_ram_042ab8be(iVar8,auStack_40,0);
          if (iVar10 == 0) goto LAB_ram_042abba4;
          FUN_ram_042ab728(auStack_40,(local_3c - param_2[1]) * iVar5 + param_3,iVar5,0);
          FUN_ram_042ab6e4(puVar9,auStack_40);
          if (iVar3 == local_34) {
            bVar1 = false;
            if (iVar8 == 0) {
              bVar1 = 0xae < param_2[3];
            }
            iVar3 = FUN_ram_042d025e(param_1);
            if ((iVar3 == 0) || (bVar1)) {
              FUN_ram_042d02c6();
              FUN_ram_042ab9d2(iVar8,0);
            }
          }
        }
        puVar9 = puVar9 + 4;
        if (iVar8 == 1) break;
        iVar8 = 1;
        iVar10 = 0xaf;
        iVar3 = 0x15d;
      }
      iVar5 = FUN_ram_042d025e(param_1);
      if (iVar5 != 0) {
        FUN_ram_042d02c6();
        bVar2 = FUN_ram_042ab892(&DAT_ram_0202dab0);
        FUN_ram_042ab9d2(0,bVar2 ^ 1);
        FUN_ram_042ab9d2(1,1);
      }
    }
  }
LAB_ram_042abba4:
  FUN_ram_042d0246(param_1);
  return;
}

