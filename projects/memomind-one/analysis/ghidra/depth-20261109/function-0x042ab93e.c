
void FUN_ram_042ab93e(uint *param_1,int param_2,undefined4 param_3)

{
  int iVar1;
  uint uVar2;
  undefined2 local_18;
  undefined2 local_16;
  undefined2 local_14;
  undefined2 local_12;
  
  gp = &DAT_ram_02011688;
  iVar1 = FUN_ram_042ab892();
  if (iVar1 == 0) {
    if ((param_2 != 0) && (iVar1 = FUN_ram_0425f292(param_2,0,1), iVar1 == 0)) {
      FUN_ram_041fd196(s_lv_port_disp_c_ram_043840a8,0x255);
      return;
    }
  }
  else {
    uVar2 = *param_1;
    *param_1 = uVar2 & 0xfffe;
    local_18 = (undefined2)(uVar2 & 0xfffe);
    local_16 = (undefined2)param_1[1];
    local_14 = (undefined2)param_1[2];
    local_12 = (undefined2)param_1[3];
    iVar1 = FUN_ram_0425f292(param_2,&local_18,param_3);
    if (iVar1 == 0) {
      FUN_ram_041fd196(s_lv_port_disp_c_ram_043840a8,0x275);
    }
    FUN_ram_042d02c6();
  }
  return;
}

