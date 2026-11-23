
undefined4 *
FUN_ram_042ac604(undefined4 param_1,int param_2,int param_3,int param_4,undefined4 param_5,
                undefined2 param_6)

{
  undefined4 *puVar1;
  undefined4 uVar2;
  
  gp = &DAT_ram_02011688;
  puVar1 = (undefined4 *)FUN_ram_02009904(0x2c,0);
  if (puVar1 == (undefined4 *)0x0) {
    FUN_ram_041fd196(s_jbd013_hw_c_ram_043840c8,0x200);
  }
  FUN_ram_020000da(puVar1,0,0x2c);
  puVar1[5] = param_3;
  if ((param_4 == 0) || (param_3 == 0)) {
    puVar1[6] = param_2;
  }
  else {
    uVar2 = FUN_ram_02009904(param_3,0);
    puVar1[6] = uVar2;
  }
  if ((param_2 != 0) && (puVar1[6] != param_2)) {
    FUN_ram_02000000(puVar1[6],param_2,param_3);
  }
  *puVar1 = param_1;
  puVar1[1] = param_5;
  *(undefined2 *)(puVar1 + 4) = param_6;
  *(char *)(puVar1 + 2) = (char)param_4;
  puVar1[10] = 0;
  return puVar1;
}

