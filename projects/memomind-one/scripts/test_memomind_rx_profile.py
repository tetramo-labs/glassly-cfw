"""Fixed profile boundaries using real RV32 links and captured OTA fixtures."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from memomind_rx_profile import *
from compile_memomind_graphics import ROOT, COMPILER, inspect_elf, compile_graphics, check_stack_usage
from build_memomind_graphics import construct_graphics, verify_graphics, _guard_final_bounds
from build_memomind_exclusive_storage import construct_exclusive_storage, verify_exclusive_storage, construct_exclusive_reader, verify_exclusive_reader
from build_memomind_flash_canary import construct_canary, verify_canary

SOURCE = ROOT/'captures/firmware/ota-1.0.3.127-glassly-text.bin'
BLOB = ROOT/'runtime/build/diagnostic-commands-001/graphics.bin'

class FixedRxProfiles(unittest.TestCase):
    def test_closed_selection_and_unchanged_stack_and_physical_guards(self):
        self.assertEqual(rx_limit(), 65536)
        self.assertEqual(rx_limit(EXTENDED_RX_PROFILE), 98304)
        for wrong in (None, '', 98304, {}, 'app-rx-128k-v1'):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError): rx_limit(wrong)
            with self.assertRaises(ValueError): compile_graphics('/unused', rx_profile=wrong)
        with self.assertRaises(ValueError): check_stack_usage(['f\t513\tstatic'])
        with self.assertRaises(ValueError): _guard_final_bounds(0x25e000+19, 100)
        with self.assertRaises(ValueError): _guard_final_bounds(100, 0x200001)

    def test_actual_linker_64_and_96_boundaries(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)
            for size in (65536, 65552, 98304, 98320):
                asm=out/'entry.S';obj=out/'entry.o';elf=out/'test.elf'
                asm.write_text('.option norvc\n.section .text.service_entry,"ax"\n.global service_entry\nservice_entry: ret\n.section .text.display_entry,"ax"\n.global display_gate\ndisplay_gate: lw a0,-112(s0)\nret\n.section .text,"ax"\n.space '+str(size-80)+'\n')
                subprocess.run([str(COMPILER/'riscv-none-elf-gcc'),'-march=rv32imafc','-mabi=ilp32f','-c',str(asm),'-o',str(obj)],check=True,capture_output=True)
                for profile in RX_PROFILES:
                    result=subprocess.run([str(COMPILER/'riscv-none-elf-gcc'),'-march=rv32imafc','-mabi=ilp32f','-nostdlib','-Wl,--no-relax','-T',str(ROOT/'runtime/graphics'/linker_name(profile)),str(obj),'-o',str(elf)],capture_output=True)
                    with self.subTest(size=size,profile=profile):
                        self.assertEqual(result.returncode==0,size<=rx_limit(profile))
                        if result.returncode==0:
                            self.assertEqual(inspect_elf(elf.read_bytes(),rx_profile=profile)[0]['memory_bytes'],size)
                            if size>65536:
                                with self.assertRaises(ValueError): inspect_elf(elf.read_bytes())
                            # RX96 cannot relax W/NOBITS/relocation protections.
                            import struct
                            changed=bytearray(elf.read_bytes());ph=struct.unpack_from('<I',changed,28)[0]
                            struct.pack_into('<I',changed,ph+24,7)
                            with self.assertRaises(ValueError): inspect_elf(changed,rx_profile=profile)
                            sh=struct.unpack_from('<I',elf.read_bytes(),32)[0]+40
                            for field,value in ((8,7),(4,8),(4,4),(4,9)):
                                changed=bytearray(elf.read_bytes())
                                struct.pack_into('<I',changed,sh+field,value)
                                with self.assertRaises(ValueError): inspect_elf(changed,rx_profile=profile)

    def test_constructor_size_boundaries(self):
        source=SOURCE.read_bytes();base=BLOB.read_bytes()
        for size in (65536,65552,98304,98320):
            blob=base+bytes(size-len(base))
            for profile in RX_PROFILES:
                with self.subTest(size=size,profile=profile):
                    if size>rx_limit(profile):
                        with self.assertRaises(ValueError): construct_graphics(source,blob,rx_profile=profile)
                    else:
                        image,manifest,proof=construct_graphics(source,blob,rx_profile=profile)
                        self.assertEqual(proof['final_bounds']['app_headroom'],323936-size)
                        self.assertLessEqual(proof['final_bounds']['rounded_payload_bytes'],0x25e000)
                        if profile==EXTENDED_RX_PROFILE:
                            self.assertEqual(manifest['rx_limit_bytes'],98304)
                            self.assertFalse(manifest['live_flashing_enabled'])

    def test_all_layers_explicit_reproduction_and_missing_wrong_profile(self):
        source=SOURCE.read_bytes();blob=BLOB.read_bytes()
        reader=blob.replace(b'H001Y-1.0.3.127-flash-canary-v1', b'H001Y-1.0.3.127-full-store-read-v1')
        reader+=bytes((-len(reader))%16)
        for construct,verify,payload in ((construct_graphics,verify_graphics,blob),
                (construct_exclusive_storage,verify_exclusive_storage,blob),
                (construct_exclusive_reader,verify_exclusive_reader,reader),
                (construct_canary,verify_canary,blob)):
            with self.subTest(construct=construct.__name__):
                image,manifest,_=construct(source,payload,rx_profile=EXTENDED_RX_PROFILE)
                self.assertTrue(manifest['format'].endswith('-rx96'))
                self.assertFalse(manifest['live_flashing_enabled'])
                self.assertEqual(verify(source,payload,manifest,rx_profile=EXTENDED_RX_PROFILE)[0],image)
                with self.assertRaises(ValueError): verify(source,payload,manifest)
                with self.assertRaises(ValueError): verify(source,payload,manifest,rx_profile='arbitrary')
                for key,value in [('rx_profile',DEFAULT_RX_PROFILE),('rx_limit_bytes',131072),('live_flashing_enabled',True)]:
                    changed=copy.deepcopy(manifest);changed[key]=value
                    with self.assertRaises(ValueError): verify(source,payload,changed,rx_profile=EXTENDED_RX_PROFILE)

    def test_default_canary_constructor_exact_historical_image_and_manifest(self):
        source=SOURCE.read_bytes();blob=BLOB.read_bytes()
        image,manifest,_=construct_canary(source,blob)
        folder=ROOT/'captures/firmware/diagnostic-commands-001'
        self.assertEqual(image,(folder/'firmware.bin').read_bytes())
        self.assertEqual(manifest,json.loads((folder/'manifest.json').read_text()))

if __name__=='__main__': unittest.main()
