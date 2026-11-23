
undefined4 FUN_ram_04236404(uint param_1,uint param_2)

{
  undefined4 *puVar1;
  int iVar2;
  uint *puVar3;
  uint uVar4;
  
  gp = &DAT_ram_02011688;
  iVar2 = FUN_ram_0200f336();
  if (DAT_ram_02011b08 != iVar2) {
    FUN_ram_041fd196(s_display_app_main_c_ram_0435f98c + 8,0x2c4);
  }
  puVar1 = &DAT_ram_02012dc8;
  do {
    puVar3 = (uint *)puVar1[1];
    if (((puVar3 != (uint *)0x0) && ((*puVar3 >> 8 & 0x3f) == param_1)) &&
       ((ushort)puVar3[1] == param_2)) {
      FUN_ram_0200f5a2(*puVar1);
      uVar4 = *(uint *)puVar1[1];
      if ((uVar4 & 0x40) == 0) {
        puVar1[1] = 0;
        FUN_ram_020099a0();
      }
      else {
        *(uint *)puVar1[1] = uVar4 | 0x80;
      }
    }
    puVar1 = puVar1 + 2;
  } while (puVar1 != (undefined4 *)&DAT_ram_02012e48);
  return 0;
}

