
void FUN_ram_042ae760(uint param_1,uint param_2)

{
  int iVar1;
  undefined4 uVar2;
  
  gp = &DAT_ram_02011688;
  if (9 < param_1) {
    iVar1 = FUN_ram_02003d5e(0xe6,5);
    param_1 = 9;
    if (iVar1 != 0) {
      uVar2 = FUN_ram_042acd24();
      FUN_ram_02003fc2(0xe6,s__T_0x_08X__jbd013_api_c_1371___J_ram_043843e0,uVar2,9);
    }
  }
  if (0x1df < param_2) {
    iVar1 = FUN_ram_02003d5e(0xe6,5);
    param_2 = 0x1df;
    if (iVar1 != 0) {
      uVar2 = FUN_ram_042acd24();
      FUN_ram_02003fc2(0xe6,s__T_0x_08X__jbd013_api_c_1375___J_ram_04384434,uVar2,0x1df);
    }
  }
  DAT_ram_02010326 = (char)param_2;
  DAT_ram_02010325 = DAT_ram_02010325 & 0x81 | (byte)((param_1 & 0x3f) << 1);
  DAT_ram_02010327 = (byte)(param_2 >> 8) & 1 | DAT_ram_02010327 & 0xfe;
  return;
}

