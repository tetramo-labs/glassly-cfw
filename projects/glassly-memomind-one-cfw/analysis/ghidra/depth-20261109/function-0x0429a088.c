
undefined4 FUN_ram_0429a088(uint param_1,undefined4 *param_2)

{
  int iVar1;
  undefined4 uVar2;
  undefined2 uVar3;
  char acStack_21 [13];
  
  gp = &DAT_ram_02011688;
  if (DAT_ram_02011e24 == 0) {
    return 0xffffffff;
  }
  uVar2 = 0xffffffff;
  if (((param_2 != (undefined4 *)0x0) && (param_1 < 0x15e)) &&
     (uVar2 = 0xfffffff9, *(char *)(DAT_ram_02011e24 + 0x34) == '\0')) {
    iVar1 = FUN_ram_0425f20e(param_1,param_1,0,acStack_21);
    uVar2 = 0xfffffffd;
    if (iVar1 != 0) {
      if (1 < (byte)(acStack_21[0] - 1U)) {
        FUN_ram_041fd196(s_gm_plugin_host_app_c_ram_04366064,0xaf);
      }
      uVar3 = 0;
      if (acStack_21[0] != '\x01') {
        uVar3 = 0xaf;
      }
      uVar2 = FUN_ram_0425f7fa(0,uVar3,0);
      *(undefined2 *)((int)param_2 + 6) = 600;
      param_2[2] = 0x14000af;
      iVar1 = DAT_ram_02011e24;
      *param_2 = uVar2;
      *(undefined2 *)(param_2 + 1) = uVar3;
      *(char *)(iVar1 + 0x34) = acStack_21[0];
      uVar2 = 0;
    }
  }
  return uVar2;
}

