#!/usr/bin/env python3
"""Actual external-tail profile uses the same pinned service/display gate ABI."""
import flash_read_gate_emulator_test as F

F.BUILD = F.ROOT / 'runtime/build/external-read-001'
F.PINNED_SHA = '6c317933ca7edef1375843375dceb18f94ef0efca93246076c92c023a56432bd'

if __name__ == '__main__':
    F.main()
