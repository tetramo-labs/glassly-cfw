
int FUN_ram_042ab8be(int param_1,int param_2,int param_3)

{
  int iVar1;
  undefined4 *puVar2;
  undefined4 uVar3;
  char cVar4;
  char local_11;
  
  gp = &DAT_ram_02011688;
  if (param_3 == 0) {
    cVar4 = (param_1 != 0) + '\x01';
    puVar2 = &DAT_ram_0202daa0 + param_1 * 4;
  }
  else {
    cVar4 = '\x04';
    puVar2 = &DAT_ram_0202dac0;
  }
  iVar1 = FUN_ram_042ab892(puVar2);
  if (iVar1 == 0) {
    iVar1 = FUN_ram_0425f20e(*(undefined2 *)(param_2 + 4),*(undefined2 *)(param_2 + 0xc),param_3,
                             &local_11);
    uVar3 = 0x292;
    if (iVar1 != 0) {
      if (local_11 == cVar4) goto LAB_ram_042ab8f0;
      uVar3 = 0x296;
    }
    FUN_ram_041fd196(s_lv_port_disp_c_ram_043840a8,uVar3);
  }
  else {
LAB_ram_042ab8f0:
    iVar1 = 1;
  }
  return iVar1;
}

