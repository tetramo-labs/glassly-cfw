
/* WARNING: Removing unreachable block (ram,0x042ae4ee) */
/* WARNING: Removing unreachable block (ram,0x042ae50c) */

undefined4 FUN_ram_042ae264(uint param_1,int *param_2)

{
  int iVar1;
  undefined4 uVar2;
  char *pcVar3;
  int iVar4;
  int iVar5;
  uint uVar6;
  uint uVar7;
  undefined *puVar8;
  int local_48;
  int local_44;
  int local_40;
  int local_3c;
  undefined4 local_38;
  int local_34 [2];
  
  gp = &DAT_ram_02011688;
  if (param_1 < 6) {
    if (param_1 == 0) {
      DAT_ram_0201031c = DAT_ram_0201031c & 0xfff8ffff;
      FUN_ram_042ad780(0,0x1e0,10,3);
      if (DAT_ram_02011e94 == '\0') {
        iVar1 = FUN_ram_042ac4be(7);
        uVar2 = 7;
        if (iVar1 == 0) {
          FUN_ram_041fd196(s_jbd013_api_c_ram_04384254,0x51a);
          return 0xb;
        }
      }
      else {
        DAT_ram_02011e95 = 1;
        uVar2 = 0;
      }
      FUN_ram_042ad52e(0,DAT_ram_0201031c._1_1_,&DAT_ram_0203d754,0x1b581,1,0,uVar2);
      gp = &DAT_ram_02011688;
      return 0;
    }
    if ((DAT_ram_02010318 & 2) != 0) {
      FUN_ram_042acefc(1);
      FUN_ram_042ad850(1,3);
      DAT_ram_02010318 = DAT_ram_02010318 & 0xfffffffd;
    }
    FUN_ram_042acfa6(9,3);
    FUN_ram_042acdb0(0x1bc5,0x1bc5,3);
    FUN_ram_042ad780(0,0x1e0,1,3);
    DAT_ram_0201031c = DAT_ram_0201031c & 0xffffffc0;
    if (param_1 == 5) {
      if ((((param_2 == (int *)0x0) ||
           (puVar8 = (undefined *)param_2[2], puVar8 == (undefined *)0x0)) ||
          (iVar1 = param_2[3], iVar1 == 0)) ||
         ((iVar5 = param_2[4], iVar5 == 0 || (iVar4 = *param_2, iVar4 != 0x25800)))) {
        iVar1 = FUN_ram_02003d5e(0xe6,5);
        if (iVar1 == 0) {
          return 0xb;
        }
        uVar2 = FUN_ram_042acd24();
        FUN_ram_02003d9c(0xe6,5,0x60002ea4,1,uVar2);
        return 0xb;
      }
    }
    else {
      iVar4 = 0;
      if (((param_1 != 1) && (iVar4 = 1, param_1 != 2)) && (iVar4 = 3, param_1 == 3)) {
        iVar4 = 2;
      }
      iVar5 = (&DAT_ram_04384fb0)[iVar4 * 6];
      if ((iVar5 < 1) ||
         (puVar8 = (&PTR_DAT_ram_02011430_ram_04384fb8)[iVar4 * 6], puVar8 == (undefined *)0x0)) {
        iVar1 = FUN_ram_02003d5e(0xe6,5);
        if (iVar1 == 0) {
          return 0xb;
        }
        uVar2 = FUN_ram_042acd24();
        pcVar3 = s__T_0x_08X__jbd013_api_c_1190___J_ram_04384330;
        goto LAB_ram_042ae2a8;
      }
      iVar1 = *(int *)(iVar4 * 0x18 + 0x4384fb4);
      iVar4 = *(int *)(iVar4 * 0x18 + 0x4384fac);
    }
    uVar7 = DAT_ram_02010318 >> 4 & 3;
    local_48 = FUN_ram_042ac604(uVar7,0,0x25801,1,0,0);
    if ((local_48 == 0) || (*(int *)(local_48 + 0x18) == 0)) {
      iVar1 = FUN_ram_02003d5e(0xe6,5);
      if (iVar1 != 0) {
        uVar2 = FUN_ram_042acd24();
        FUN_ram_02003d9c(0xe6,5,0x60002ea8,1,uVar2);
      }
    }
    else {
      local_44 = 0x25801;
      local_3c = 0;
      local_40 = iVar5;
      iVar1 = FUN_ram_042383e0(*(int *)(local_48 + 0x18),&local_44,iVar1,&local_40,puVar8,5,1,
                               &local_3c,&PTR_FUN_ram_042acf90_ram_02011438);
      if ((iVar1 == 0) &&
         ((param_1 != 5 ||
          ((((iVar4 == local_44 && (iVar5 == local_40)) && ((local_3c == 1 || (local_3c == 4)))) &&
           (iVar4 = FUN_ram_0434cb6e(*(undefined4 *)(local_48 + 0x18),iVar4), iVar4 == param_2[1])))
          ))) {
        uVar6 = local_44 / 0x140;
        local_38 = 0;
        *(int *)(local_48 + 0x14) = local_44;
        local_34[0] = FUN_ram_042ac604(uVar7,0,5,1,uVar7,0);
        if ((local_34[0] == 0) || (*(int *)(local_34[0] + 0x18) == 0)) {
          iVar1 = FUN_ram_02003d5e(0xe6,5);
          if (iVar1 != 0) {
            uVar2 = FUN_ram_042acd24();
            FUN_ram_02003d9c(0xe6,5,0x60002eac,1,uVar2);
          }
        }
        else {
          FUN_ram_042acc74(0,(int)(0x1e0 - (uVar6 & 0xffff)) / 2 & 0xffff);
          FUN_ram_042ad21a(&local_38,local_34[0]);
          FUN_ram_042ad21a(local_34,local_48);
          iVar1 = FUN_ram_042ac604(3,0,1,1,0,2);
          if ((iVar1 != 0) && (*(undefined1 **)(iVar1 + 0x18) != (undefined1 *)0x0)) {
            **(undefined1 **)(iVar1 + 0x18) = 0x97;
            FUN_ram_042ad21a(&local_48,iVar1);
            FUN_ram_042ac430(local_38);
            gp = &DAT_ram_02011688;
            DAT_ram_0201031c = DAT_ram_0201031c & 0xfff8ffff | (param_1 & 7) << 0x10;
            return 0;
          }
          iVar5 = FUN_ram_02003d5e(0xe6,5);
          if (iVar5 != 0) {
            uVar2 = FUN_ram_042acd24();
            FUN_ram_02003d9c(0xe6,5,0x60002eb0,1,uVar2);
          }
          FUN_ram_042acf62(iVar1);
        }
        FUN_ram_042acf62(local_34[0]);
      }
      else {
        iVar4 = FUN_ram_02003d5e(0xe6,5);
        if (iVar4 != 0) {
          uVar2 = FUN_ram_042acd24();
          FUN_ram_02003fc2(0xe6,s__T_0x_08X__jbd013_api_c_1231___J_ram_04384380,uVar2,iVar1,local_3c
                           ,local_40,iVar5);
        }
      }
    }
    FUN_ram_042acf62(local_48);
  }
  else {
    iVar1 = FUN_ram_02003d5e(0xe6,5);
    if (iVar1 == 0) {
      return 0xb;
    }
    uVar2 = FUN_ram_042acd24();
    pcVar3 = s__T_0x_08X__jbd013_api_c_1277___J_ram_043842f0;
LAB_ram_042ae2a8:
    FUN_ram_02003fc2(0xe6,pcVar3,uVar2,param_1);
  }
  return 0xb;
}

