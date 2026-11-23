
void FUN_ram_042ad21a(int *param_1,int param_2)

{
  int iVar1;
  int iVar2;
  
  gp = &DAT_ram_02011688;
  if ((param_1 != (int *)0x0) && (param_2 != 0)) {
    iVar2 = *param_1;
    if (*param_1 == 0) {
      *param_1 = param_2;
    }
    else {
      do {
        iVar1 = iVar2;
        iVar2 = *(int *)(iVar1 + 0x28);
      } while (iVar2 != 0);
      *(int *)(iVar1 + 0x28) = param_2;
    }
  }
  return;
}

