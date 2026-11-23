#!/usr/bin/env python3
"""Actual external-tail reader profile; retain all base reader scenarios."""
import flash_read_runtime_emulator_test as F

F.BUILD = F.ROOT / 'runtime/build/external-read-001'
F.PINNED_SHA = '6c317933ca7edef1375843375dceb18f94ef0efca93246076c92c023a56432bd'
F.RANGES = (*F.RANGES, (1, 0x700000, 0x800000))

if __name__ == '__main__':
    F.main()
