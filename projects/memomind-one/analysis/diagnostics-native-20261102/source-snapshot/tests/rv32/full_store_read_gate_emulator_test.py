#!/usr/bin/env python3
"""Full-store profile's stock-preserving gates; C entry bodies mocked."""
import flash_read_gate_emulator_test as F
F.BUILD=F.ROOT/'runtime/build/full-store-read-001'
F.PINNED_SHA='83290f4c3d300b3f479bcd60865ffb5cc29b55e5887e635fac6f0d0d208d352b'
if __name__=='__main__':F.main()
