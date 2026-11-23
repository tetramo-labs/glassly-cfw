
/* WARNING: Removing unreachable block (ram,0x042ef4fc) */
/* WARNING: Restarted to delay deadcode elimination for space: ram */

int FUN_ram_042eeea6(void)

{
  byte bVar1;
  int iVar2;
  undefined4 uVar3;
  uint uVar4;
  int iVar5;
  int iVar6;
  char *pcVar7;
  int iVar8;
  int iVar9;
  int iVar10;
  byte *pbVar11;
  uint uVar12;
  undefined4 uVar13;
  uint uVar14;
  byte bVar15;
  uint uVar16;
  uint uVar17;
  undefined1 *puVar18;
  int iVar19;
  int iVar20;
  short sVar21;
  char cVar22;
  int local_64;
  undefined1 local_5a;
  char local_59;
  char local_58 [4];
  int local_54;
  int local_50;
  ushort local_4c;
  ushort local_4a;
  ushort local_48;
  ushort local_46;
  ushort local_44;
  
  gp = &DAT_ram_02011688;
  if ((DAT_ram_02012100 == 0) && (DAT_ram_02012100 = FUN_ram_0200ebf2(0xe1), DAT_ram_02012100 == 0))
  {
    iVar2 = FUN_ram_02003d5e(0xe6,5);
    if (iVar2 != 0) {
      uVar3 = FUN_ram_042ec12e();
      uVar13 = 0x60003a10;
LAB_ram_042eef04:
      FUN_ram_02003d9c(0xe6,5,uVar13,1,uVar3);
    }
  }
  else if ((DAT_ram_02012120 == 0) &&
          (DAT_ram_02012120 = FUN_ram_0200f45a(0xe1,1,&LAB_ram_042ec6c2,0), DAT_ram_02012120 == 0))
  {
    iVar2 = FUN_ram_02003d5e(0xe6,5);
    if (iVar2 != 0) {
      uVar3 = FUN_ram_042ec12e();
      uVar13 = 0x60003a14;
      goto LAB_ram_042eef04;
    }
  }
  else {
    if ((DAT_ram_0201211c != 0) ||
       (DAT_ram_0201211c = FUN_ram_0200f45a(0xe1,1,FUN_ram_042ec654,0), DAT_ram_0201211c != 0)) {
      if (DAT_ram_02012100 != 0) {
        FUN_ram_0200ec3a();
      }
      if (DAT_ram_02012104 != '\0') {
        if (DAT_ram_02012100 != 0) {
          FUN_ram_0200ecb2();
        }
        iVar2 = FUN_ram_02003d5e(0xe6,5);
        iVar19 = 9;
        if (iVar2 == 0) {
          gp = &DAT_ram_02011688;
          return 9;
        }
        uVar3 = FUN_ram_042ec12e();
        uVar13 = 0x60003a20;
        goto LAB_ram_042eef34;
      }
      DAT_ram_02012104 = '\x01';
      if (DAT_ram_02012120 != 0) {
        FUN_ram_0200f5a2();
      }
      if (DAT_ram_02012100 != 0) {
        FUN_ram_0200ecb2();
      }
      FUN_ram_042ec0ea();
      iVar2 = FUN_ram_042442e4();
      uVar4 = FUN_ram_0433c3c6(0);
      if (uVar4 < iVar2 + 0x16a04U) {
        iVar19 = FUN_ram_02003d5e(0xe6,5);
        if (iVar19 != 0) {
          uVar3 = FUN_ram_042ec12e();
          FUN_ram_02003fc2(0xe6,s__T_0x_08X__bt_data_report_c_3276_ram_04393c1c,uVar3,iVar2 + 0xea04
                           ,0x8000,uVar4);
        }
        iVar20 = 2;
        goto LAB_ram_042ef17e;
      }
      iVar19 = FUN_ram_0433c320(0x100,0);
      iVar5 = FUN_ram_0433c320(0x2904,0);
      iVar6 = FUN_ram_0433c320(iVar2,0x10000);
      iVar2 = FUN_ram_0433c320(0xc000,0);
      if ((((iVar19 == 0) || (iVar5 == 0)) || (iVar2 == 0)) || (iVar6 == 0)) {
        iVar20 = FUN_ram_02003d5e(0xe6,5);
        if (iVar20 != 0) {
          uVar3 = FUN_ram_042ec12e();
          FUN_ram_02003d9c(0xe6,5,0x60003a24,1,uVar3);
        }
        iVar20 = 2;
        if (iVar19 != 0) goto LAB_ram_042ef2b6;
LAB_ram_042ef14e:
        local_64 = 0;
        if (iVar5 != 0) goto LAB_ram_042ef152;
      }
      else {
        iVar20 = FUN_ram_0425f7fa(0,0,0);
        if (iVar20 == 0) {
          iVar20 = FUN_ram_02003d5e(0xe6,5);
          if (iVar20 != 0) {
            uVar3 = FUN_ram_042ec12e();
            FUN_ram_02003d9c(0xe6,5,0x60003a28,1,uVar3);
          }
          pcVar7 = s_Failed_to_get_screen_data_ram_04393c94;
LAB_ram_042ef20e:
          FUN_ram_042eebfa(pcVar7);
LAB_ram_042ef2b4:
          iVar20 = 0xb;
LAB_ram_042ef2b6:
          FUN_ram_020099a0(iVar19);
          goto LAB_ram_042ef14e;
        }
        FUN_ram_020000da(local_58,0,0x18);
        iVar8 = FUN_ram_0425f20e(0,0,1,&local_59);
        cVar22 = '\0';
        if (iVar8 != 0) {
          FUN_ram_0425f808(local_58);
          if ((((local_58[0] == '\0') || (local_54 == 0)) ||
              ((local_50 == 0 || ((local_4a == 0 || (local_48 == 0)))))) ||
             (iVar8 = 0, local_4c == 0)) {
            cVar22 = '\0';
            FUN_ram_042ec56c(local_59);
          }
          else {
            do {
              cVar22 = local_58[0];
              if (*(char *)(local_54 + iVar8) != '\0') goto LAB_ram_042ef2d4;
              iVar8 = iVar8 + 1;
            } while (local_50 != iVar8);
            cVar22 = '\0';
LAB_ram_042ef2d4:
            FUN_ram_042ec56c(local_59);
          }
        }
        uVar4 = 0;
        sVar21 = 0;
        iVar8 = 0;
        do {
          local_59 = '\0';
          iVar9 = FUN_ram_0425f20e(uVar4 & 0xffff,(uVar4 & 0xffff) + 0x22 & 0xffff,0,&local_5a);
          if (iVar9 == 0) goto LAB_ram_042ef2b4;
          if (cVar22 != '\0') {
            iVar9 = FUN_ram_0425f20e(0,0,1,&local_59);
            if (iVar9 == 0) {
              FUN_ram_042ec56c(local_5a);
              goto LAB_ram_042ef2b4;
            }
            FUN_ram_0425f808(local_58);
          }
          uVar16 = 0;
          iVar9 = uVar4 * 0x140 + iVar20;
          do {
            FUN_ram_02000000(uVar16 * 300 + iVar5,iVar9,300);
            uVar16 = uVar16 + 1;
            iVar9 = iVar9 + 0x140;
          } while (uVar16 < 0x23);
          if ((cVar22 != '\0') && (local_58[0] != '\0')) {
            for (uVar16 = 0; iVar9 = local_54, uVar16 < local_48; uVar16 = uVar16 + 1 & 0xffff) {
              iVar10 = local_44 + uVar16;
              if (((int)uVar4 <= iVar10) && (iVar10 < (int)(uVar4 + 0x23))) {
                uVar17 = (uint)local_4c;
                iVar10 = (iVar10 - uVar4) * 300 + iVar5;
                FUN_ram_020000da(iVar10,0,300);
                for (uVar14 = 0; uVar14 < local_4a; uVar14 = uVar14 + 1 & 0xffff) {
                  uVar12 = local_46 + uVar14;
                  if (uVar12 < 600) {
                    bVar15 = *(byte *)((uVar14 >> 1) + iVar9 + uVar17 * uVar16);
                    bVar1 = bVar15 >> 4;
                    if ((uVar14 & 1) != 0) {
                      bVar1 = bVar15 & 0xf;
                    }
                    pbVar11 = (byte *)(((int)uVar12 >> 1) + iVar10);
                    bVar15 = *pbVar11;
                    if ((uVar12 & 1) == 0) {
                      bVar15 = bVar15 & 0xf;
                      bVar1 = bVar1 << 4;
                    }
                    else {
                      bVar15 = bVar15 & 0xf0;
                    }
                    *pbVar11 = bVar15 | bVar1;
                  }
                }
              }
            }
          }
          if (local_59 != '\0') {
            FUN_ram_042ec56c();
          }
          FUN_ram_042ec56c(local_5a);
          if (0xbfff < iVar8 + 5U) {
            iVar20 = FUN_ram_02003d5e(0xe6,5);
            if (iVar20 != 0) {
              uVar3 = FUN_ram_042ec12e();
              FUN_ram_02003fc2(0xe6,s__T_0x_08X__bt_data_report_c_3377_ram_04393cb0,uVar3,sVar21,
                               iVar8,0xc000);
            }
            pcVar7 = s_stream_overflow_ram_04393d10;
            goto LAB_ram_042ef20e;
          }
          iVar9 = FUN_ram_04244330(iVar6,iVar5,iVar8 + 5U + iVar2,0x2904,0xbffb - iVar8,1);
          if (0xfffe < iVar9 - 1U) {
            iVar20 = FUN_ram_02003d5e(0xe6,5);
            if (iVar20 != 0) {
              uVar3 = FUN_ram_042ec12e();
              FUN_ram_02003fc2(0xe6,s__T_0x_08X__bt_data_report_c_3393_ram_04393d20,uVar3,sVar21,
                               0x2904,0xbffb - iVar8,iVar9);
            }
            pcVar7 = s_LZ4_band_failed_ram_04393d90;
            goto LAB_ram_042ef20e;
          }
          puVar18 = (undefined1 *)(iVar2 + iVar8);
          *puVar18 = (char)sVar21;
          sVar21 = sVar21 + 1;
          puVar18[2] = 0x23;
          puVar18[1] = 0;
          puVar18[3] = (char)((uint)iVar9 >> 8);
          puVar18[4] = (char)iVar9;
          iVar8 = iVar8 + iVar9 + 5;
          uVar4 = uVar4 + 0x23;
        } while (sVar21 != 10);
        uVar4 = (iVar8 + 0x17fU) / 0x180;
        FUN_ram_041fe8c4(iVar19,0x100,s___cmd_id___d__width___u__height__ram_04393da0,0x66,600,0x15e
                         ,600,0x23,10,0x19a28,iVar8,uVar4);
        local_64 = FUN_ram_042ee9e2(0,0,0xfffe,iVar19);
        if (local_64 == 0) {
          iVar20 = FUN_ram_02003d5e(0xe6,5);
          if (iVar20 != 0) {
            uVar3 = FUN_ram_042ec12e();
            FUN_ram_02003d9c(0xe6,5,0x60003a2c,1,uVar3);
          }
          pcVar7 = s_START_frame_send_failed_ram_04393e6c;
          goto LAB_ram_042ef20e;
        }
        DAT_ram_0205b12c = 0x2580000;
        DAT_ram_0205b130 = 0x258015e;
        DAT_ram_0205b110 = 1;
        DAT_ram_0205b124 = 0;
        DAT_ram_0205b128 = 0x19a28;
        DAT_ram_0205b134 = 1;
        DAT_ram_0205b114 = iVar2;
        DAT_ram_0205b118 = iVar19;
        DAT_ram_0205b11c = iVar8;
        DAT_ram_0205b120 = uVar4;
        iVar2 = FUN_ram_042ec2a4(0x28);
        iVar20 = 0;
        if (iVar2 == 0) {
          FUN_ram_042eebfa(s_schedule_step_failed_ram_04393ba4);
          FUN_ram_042ec396(0xb);
          iVar20 = 0xb;
        }
        iVar2 = 0;
LAB_ram_042ef152:
        FUN_ram_020099a0(iVar5);
      }
      if (iVar2 != 0) {
        FUN_ram_020099a0(iVar2);
      }
      if (iVar6 != 0) {
        FUN_ram_020099a0(iVar6);
      }
      if (local_64 != 0) {
        gp = &DAT_ram_02011688;
        return iVar20;
      }
LAB_ram_042ef17e:
      if (DAT_ram_02012100 != 0) {
        FUN_ram_0200ec3a();
      }
      DAT_ram_02012104 = '\0';
      if (((iVar20 == 0) && (DAT_ram_0201210c != 0)) && (DAT_ram_02012120 != 0)) {
        FUN_ram_0200f4d8(DAT_ram_02012120,1000);
      }
      if (DAT_ram_02012100 == 0) {
        gp = &DAT_ram_02011688;
        return iVar20;
      }
      FUN_ram_0200ecb2();
      gp = &DAT_ram_02011688;
      return iVar20;
    }
    iVar2 = FUN_ram_02003d5e(0xe6,5);
    if (iVar2 != 0) {
      uVar3 = FUN_ram_042ec12e();
      uVar13 = 0x60003a18;
      goto LAB_ram_042eef04;
    }
  }
  iVar2 = FUN_ram_02003d5e(0xe6,5);
  iVar19 = 2;
  if (iVar2 == 0) {
    gp = &DAT_ram_02011688;
    return 2;
  }
  uVar3 = FUN_ram_042ec12e();
  uVar13 = 0x60003a1c;
LAB_ram_042eef34:
  FUN_ram_02003d9c(0xe6,5,uVar13,1,uVar3);
  return iVar19;
}

