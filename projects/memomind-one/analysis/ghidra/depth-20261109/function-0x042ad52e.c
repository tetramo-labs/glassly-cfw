
/* WARNING: Removing unreachable block (ram,0x042ad5fe) */
/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void FUN_ram_042ad52e(int param_1,int param_2,undefined4 param_3,uint param_4,int param_5,
                     int param_6,uint param_7)

{
  undefined4 uVar1;
  int iVar2;
  int iVar3;
  uint uVar4;
  uint uVar5;
  int iVar6;
  int local_34 [3];
  
  gp = &DAT_ram_02011688;
  if (((byte)DAT_ram_02010318 & 0x30) == 0) goto LAB_ram_042ad55a;
  uVar4 = DAT_ram_0201031c & 0x3f;
  local_34[0] = 0;
  iVar2 = (int)((0x28 - uVar4) * 0x10000) >> 0x10;
  if (param_6 == 0) {
    iVar6 = (int)(short)param_2;
    local_34[0] = FUN_ram_042ad2c4((int)(short)param_1,iVar6,iVar2,(int)(short)param_1,iVar6,uVar4,
                                   param_3);
    if ((_DAT_ram_02010324 & 0x100) != 0) {
      iVar3 = (_DAT_ram_02010324 >> 0x10 & 0x1ff) + (DAT_ram_0201031c >> 8 & 0xff);
      if (iVar3 < iVar6) {
        if (iVar6 <= iVar3 + 0xcb) goto LAB_ram_042ad610;
      }
      else if (iVar3 <= (int)((param_4 / 0x140 + param_2 + 1) * 0x10000) >> 0x10) {
LAB_ram_042ad610:
        uVar5 = _DAT_ram_02010324 >> 9 & 0x3f;
        if (((param_7 | DAT_ram_02011e94) & 4) == 0) {
          FUN_ram_041fd196(s_jbd013_api_c_ram_04384254,0x1e4);
        }
        uVar1 = FUN_ram_042ad2c4(uVar5 + 10,iVar3,iVar2,10 - uVar5,iVar3,uVar4,&DAT_ram_0202dad0,
                                 0xfc81);
        FUN_ram_042ad21a(local_34,uVar1);
      }
    }
  }
  else {
    uVar5 = _DAT_ram_02010324 >> 9 & 0x3f;
    iVar6 = (int)(((_DAT_ram_02010324 >> 0x10 & 0x1ff) + (DAT_ram_0201031c >> 8 & 0xff) + param_2) *
                 0x10000) >> 0x10;
    local_34[0] = FUN_ram_042ad2c4((int)((param_1 + uVar5 + 10) * 0x10000) >> 0x10,iVar6,iVar2,
                                   (int)(((param_1 - uVar5) + 10) * 0x10000) >> 0x10,iVar6,uVar4,
                                   param_3);
  }
  if (((byte)DAT_ram_02010318 & 8) != 0) {
    uVar5 = _DAT_ram_02010324 >> 9 & 0x3f;
    iVar2 = (_DAT_ram_02010324 >> 0x10 & 0x1ff) + (DAT_ram_0201031c >> 8 & 0xff);
    uVar1 = FUN_ram_042ad23a(((0x28 - uVar4 & 0xffff) - uVar5) + 10 & 0xffff,iVar2,uVar5,2);
    FUN_ram_042ad21a(local_34,uVar1);
    uVar1 = FUN_ram_042ad23a((uVar4 + 0x24e) - uVar5 & 0xffff,iVar2 + 0xc9,uVar5,1);
    FUN_ram_042ad21a(local_34,uVar1);
    DAT_ram_02010318._0_1_ = (byte)DAT_ram_02010318 & 0xf7;
  }
  if (local_34[0] != 0) {
    if (param_5 == 0) {
      if (param_7 != 0) {
        FUN_ram_042ac59e(local_34[0],param_7);
      }
    }
    else {
      iVar2 = FUN_ram_042ac604(3,0,1,1,0,2);
      **(undefined1 **)(iVar2 + 0x18) = 0x97;
      FUN_ram_042ad21a(local_34,iVar2);
      if (param_7 != 0) {
        *(char *)(iVar2 + 9) = (char)param_7;
      }
    }
    FUN_ram_042ac430(local_34[0]);
    gp = &DAT_ram_02011688;
    return;
  }
LAB_ram_042ad55a:
  FUN_ram_042ac360(param_7);
  return;
}

