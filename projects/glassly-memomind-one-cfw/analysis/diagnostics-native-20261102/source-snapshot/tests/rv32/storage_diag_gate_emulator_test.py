#!/usr/bin/env python3
"""Diagnostic profile retains the same stock-preserving service/display gates."""
import flash_read_gate_emulator_test as F
F.BUILD=F.ROOT/'runtime/build/storage-diag-001'
F.PINNED_SHA='265f8837b2b939930434253f7be63a1155190fef701c57d8c123d482a66725eb'
if __name__=='__main__':F.main()
