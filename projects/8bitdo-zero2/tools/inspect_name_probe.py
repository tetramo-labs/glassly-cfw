"""Execute the actual USB product-string callback for stock and name probe.

Unicorn only: no hardware, transport stubs, or instruction modifications.
"""
import json
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC
from build_name_probe import build, OLD, NEW
from firmware_image import ROOT, load_stock
from startup import reconstruct


def verify():
    _, patched, manifest = build()
    cases = []
    for payload, expected in ((load_stock()[2][1], OLD), (patched, NEW)):
        for mode in range(5):
            for index in (0, 1):
                uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
                uc.mem_map(0x1018000, 0x12000)
                uc.mem_write(0x1018000, payload)
                uc.mem_map(0x20000, 0x10000)
                for address, data in reconstruct(payload)[1].items():
                    uc.mem_write(address, data)
                uc.mem_write(0x20060, bytes([mode]))
                uc.reg_write(UC_ARM_REG_R0, index)
                uc.reg_write(UC_ARM_REG_R1, 0x2f000)
                uc.reg_write(UC_ARM_REG_SP, 0x2ff00)
                uc.reg_write(UC_ARM_REG_LR, 0x1018101)
                uc.emu_start(0x10221c1, 0x1018100, count=5000)
                if uc.reg_read(UC_ARM_REG_PC) != 0x1018100 or uc.reg_read(UC_ARM_REG_SP) != 0x2ff00:
                    raise AssertionError('USB name callback failed to return cleanly')
                pointer = uc.reg_read(UC_ARM_REG_R0)
                length = int.from_bytes(uc.mem_read(0x2f000, 2), 'little')
                descriptor = bytes(uc.mem_read(pointer, length))
                name = expected.decode()
                if index and mode in (0, 2):
                    name = {0: 'Pro Controller', 2: 'Wireless Controller'}[mode]
                wanted = name.encode('utf-16le')
                if descriptor != bytes([len(wanted)+2, 3]) + wanted:
                    raise AssertionError('USB product descriptor differs from expected name')
                cases.append(dict(patched=payload == patched, mode=mode, index=index, name=name))
    return dict(kind='Offline execution of unmodified callback and string converter',
                package_sha256=manifest['package_sha256'], cases=cases,
                hardware_accessed=False)


if __name__ == '__main__':
    report = verify()
    out = ROOT / 'build/name-probe/usb-descriptor-emulation.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(f'Passed {len(report["cases"])} stock/patched USB descriptor cases; no hardware accessed.')
