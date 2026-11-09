
void FUN_ram_042ae8b6(void)

{
  int iVar1;
  
  gp = &DAT_ram_02011688;
  iVar1 = FUN_ram_0421111c();
  if ((iVar1 == 0) && ((DAT_ram_02010318 & 2) != 0)) {
    if ((DAT_ram_02010318 >> 2 & 1) == 0) {
      FUN_ram_042ae81c();
      DAT_ram_02010318 = DAT_ram_02010318 | 4;
    }
    FUN_ram_042acefc(1);
    FUN_ram_042ad850(1,3);
    FUN_ram_042adc2a(0);
    DAT_ram_02010318 = DAT_ram_02010318 & 0xfffffffd;
  }
  return;
}

