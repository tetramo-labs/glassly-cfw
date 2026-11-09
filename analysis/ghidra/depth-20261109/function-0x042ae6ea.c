
void FUN_ram_042ae6ea(int param_1)

{
  gp = &DAT_ram_02011688;
  DAT_ram_02010325 = DAT_ram_02010325 & 0xfe | (byte)param_1 & 1;
  if (param_1 == 0) {
    FUN_ram_042adc2a();
    FUN_ram_020000da(&DAT_ram_0202dad0,0,0xfc81);
    DAT_ram_02010318._0_1_ = (byte)DAT_ram_02010318 & 0xf7;
  }
  else {
    DAT_ram_02010318._0_1_ = (byte)DAT_ram_02010318 | 8;
  }
  return;
}

