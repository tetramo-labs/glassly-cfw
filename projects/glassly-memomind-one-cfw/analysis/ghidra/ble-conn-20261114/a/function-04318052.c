
void FUN_ram_04318052(int param_1)

{
  undefined1 auStack_18 [6];
  undefined1 local_12;
  
  gp = &DAT_ram_02011688;
  if (param_1 == 0) {
    FUN_ram_041fd196(s_wq_ble_c_ram_04395488,0x12a);
  }
  local_12 = 0;
  FUN_ram_02000000(auStack_18,param_1,6);
  FUN_ram_043199d2(0x175,auStack_18,7);
  return;
}

