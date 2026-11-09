
void FUN_ram_042ae81c(void)

{
  float fVar1;
  int iVar2;
  int iVar3;
  
  gp = &DAT_ram_02011688;
  iVar2 = FUN_ram_042ad198(2,&DAT_ram_02010328,&DAT_ram_0435bdf0);
  iVar3 = FUN_ram_042ad198(1,&DAT_ram_0201033e,s_right_ram_0435bde8);
  if ((iVar2 != 0) || (iVar3 != 0)) {
    DAT_ram_02010320 = 0;
    DAT_ram_02010324 = 0;
    fVar1 = (float)DAT_ram_02010318._2_2_ / DAT_ram_02011134;
    if (iVar2 != 0) {
      FUN_ram_042acfea(2,1);
    }
    if (iVar3 != 0) {
      FUN_ram_042acfea(fVar1,1,1);
      return;
    }
  }
  return;
}

