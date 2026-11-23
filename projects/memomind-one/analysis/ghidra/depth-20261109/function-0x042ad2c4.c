
undefined4
FUN_ram_042ad2c4(undefined2 param_1,undefined2 param_2,undefined4 param_3,undefined2 param_4,
                undefined2 param_5,undefined4 param_6,int param_7,uint param_8)

{
  undefined2 uVar1;
  undefined2 uVar2;
  undefined2 uVar3;
  undefined2 uVar4;
  uint *puVar5;
  int iVar6;
  undefined4 uVar7;
  uint uVar8;
  undefined2 local_58;
  undefined2 local_56;
  undefined2 local_54;
  undefined2 local_52 [3];
  undefined4 local_4c;
  int local_48;
  undefined4 local_44;
  undefined4 local_40;
  uint local_3c;
  uint local_38 [4];
  
  gp = &DAT_ram_02011688;
  local_58 = param_5;
  local_56 = param_4;
  local_54 = param_2;
  local_52[0] = param_1;
  FUN_ram_042acca0(local_52,&local_54);
  FUN_ram_042acca0(&local_56,&local_58,param_6);
  uVar4 = local_52[0];
  uVar3 = local_54;
  uVar2 = local_56;
  uVar1 = local_58;
  local_4c = 0;
  if (((DAT_ram_02010318 & 0x30) == 0x30) && (5 < param_8)) {
    local_48 = FUN_ram_042ac604(2,0,5,1,2,2);
    FUN_ram_042acc74(uVar4,uVar3,*(undefined4 *)(local_48 + 0x18));
    FUN_ram_042ad21a(&local_4c,local_48);
    local_44 = FUN_ram_042ac604(3,0,5,1,3,0);
    uVar7 = *(undefined4 *)(local_44 + 0x18);
    local_3c = CONCAT22(local_3c._2_2_,uVar2);
    local_38[0] = CONCAT22(local_38[0]._2_2_,uVar1);
    FUN_ram_042acca0(&local_3c,local_38,10);
    FUN_ram_042acc74(local_3c & 0xffff,local_38[0] & 0xffff,uVar7);
    FUN_ram_042ad21a(&local_48,local_44);
    local_40 = FUN_ram_042ac604(3,param_7 + 5,param_8 - 5,0,0,0);
    FUN_ram_042ad21a(&local_44,local_40);
    local_3c = FUN_ram_042ac604(2,0,5,1,2,0);
    FUN_ram_042acc74(uVar4,uVar3,*(undefined4 *)(local_3c + 0x18));
    FUN_ram_042ad21a(&local_40,local_3c);
    uVar7 = FUN_ram_042ac604(2,param_7,6,0,0,0);
    FUN_ram_042ad21a(&local_3c,uVar7);
    local_38[0] = FUN_ram_042ac604(1,0,5,1,1,0);
    FUN_ram_042acc74(uVar2,uVar1,*(undefined4 *)(local_38[0] + 0x18));
    FUN_ram_042ad21a(&local_40,local_38[0]);
    uVar7 = FUN_ram_042ac604(1,param_7,6,0,0,0);
    FUN_ram_042ad21a(local_38,uVar7);
  }
  else {
    local_38[0] = 2;
    local_44 = CONCAT22(local_56,local_52[0]);
    local_38[1] = 1;
    local_40 = CONCAT22(local_58,local_54);
    puVar5 = local_38;
    iVar6 = 0;
    do {
      uVar8 = *puVar5;
      if ((DAT_ram_02010318 >> 4 & 3 & uVar8) != 0) {
        uVar7 = 0;
        if ((DAT_ram_02010318 & 0x30) != 0x30) {
          uVar7 = 2;
        }
        local_3c = FUN_ram_042ac604(uVar8,0,5,1,uVar8,uVar7);
        FUN_ram_042acc74(*(undefined2 *)((int)local_38 + iVar6 + -0xc),
                         *(undefined2 *)((int)local_38 + iVar6 + -8),
                         *(undefined4 *)(local_3c + 0x18));
        FUN_ram_042ad21a(&local_4c,local_3c);
        uVar7 = FUN_ram_042ac604(uVar8,param_7,param_8,0,0,0);
        FUN_ram_042ad21a(&local_3c,uVar7);
      }
      iVar6 = iVar6 + 2;
      puVar5 = puVar5 + 1;
    } while (iVar6 != 4);
  }
  return local_4c;
}

