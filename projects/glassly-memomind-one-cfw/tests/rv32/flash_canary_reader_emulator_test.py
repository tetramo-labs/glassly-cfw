#!/usr/bin/env python3
"""Retain actual full reader/diagnostic coverage against the canary image."""
import full_store_read_runtime_emulator_test as suite
suite.BUILD=suite.F.ROOT/'runtime/build/flash-canary-004'
suite.PINNED_SHA='c30da32f8759627aa85247757d0ccae67466a730b5802827246fe2d91a699992'
suite.PROFILE='H001Y-1.0.3.127-flash-canary-v1'
class CanaryReader(suite.FullMachine):
 def native(self,name,args):
  # Canary probe's larger truthful registry identity uses owned scratch. The
  # bounded reader itself continues to allocate exactly1024 after request free.
  if name=='try_alloc' and args[0]!=1024:
   assert args[0]<768 and not self.request_releases
   return suite.G.Machine.native(self,name,args)
  return super().native(name,args)
suite.FullMachine=CanaryReader
if __name__=='__main__':suite.main()
