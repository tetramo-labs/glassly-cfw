#!/usr/bin/env python3
"""Reconstruct the offline RX96 candidate and retain exact source/artifact pins."""
import hashlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from build_memomind_flash_canary import verify_canary
from memomind_rx_profile import EXTENDED_RX_PROFILE
from memomind_ota import unpack_ota

def sha(data): return hashlib.sha256(data).hexdigest()
def main():
    out=Path(sys.argv[1]);assert not out.exists()
    buildpath=ROOT/'runtime/build/diagnostic-rx96-001'
    build=json.loads((buildpath/'build.json').read_text())
    legacy=json.loads((ROOT/'runtime/build/diagnostic-rx64-reproduction-001/build.json').read_text())
    candidate=ROOT/'captures/firmware/diagnostic-rx96-001'
    manifest=json.loads((candidate/'manifest.json').read_text())
    source=(ROOT/'captures/firmware/ota-1.0.3.127-glassly-text.bin').read_bytes()
    blob=(buildpath/'graphics.bin').read_bytes()
    assert sha(blob)==build['blob_sha256']==legacy['blob_sha256']=='c1d8a1ffdd4f2799de4149d2e113527b29716886f6530549e56f68f61333d3b3'
    image,proof=verify_canary(source,blob,manifest,rx_profile=EXTENDED_RX_PROFILE)
    assert image==(candidate/'firmware.bin').read_bytes()
    assert image==(ROOT/'captures/firmware/diagnostic-commands-001/firmware.bin').read_bytes()
    try: verify_canary(source,blob,manifest)
    except ValueError: pass
    else: raise AssertionError('Default profile accepted RX96 manifest')
    _,streams=unpack_ota(image)
    assert streams[3]['raw'][:256]==(candidate/'expected-app-header.bin').read_bytes()
    changed=['scripts/memomind_rx_profile.py','runtime/graphics/graphics_rx96.ld',
             'scripts/compile_memomind_graphics.py','scripts/build_memomind_graphics.py',
             'scripts/build_memomind_exclusive_storage.py','scripts/build_memomind_flash_canary.py',
             'scripts/test_memomind_rx_profile.py']
    drift=[p for p,d in build['source_sha256'].items() if sha((ROOT/p).read_bytes())!=d]
    assert not drift
    logs={'profile-tests.log':5,'existing-tests.log':17,'exclusive-tests.log':11,'canary-tests.log':4}
    for p,n in logs.items():
        text=(Path(__file__).parent/p).read_text();assert '\nOK\n' in text and f'Ran {n} tests' in text
    gates=json.loads((Path(__file__).parent/'gates.json').read_text());assert gates['passed'] and gates['cases']==7955
    payload=len(image)-18;raw=len(streams[3]['raw'])
    report=dict(passed=True,offline_only=True,device_actions=False,source_drift=drift,
        profile=EXTENDED_RX_PROFILE,max_rx_bytes=98304,default_max_rx_bytes=65536,
        runtime=dict(path=str(buildpath.relative_to(ROOT)),bytes=len(blob),sha256=sha(blob),remaining_rx_bytes=98304-len(blob),
                     historical_default_binary_identical=True,elf_sha256=build['elf_sha256']),
        ota=dict(path=str(candidate.relative_to(ROOT)),bytes=len(image),sha256=sha(image),
                 historical_diagnostic_image_identical=True,manifest_sha256=sha((candidate/'manifest.json').read_bytes()),
                 format=manifest['format'],live_flashing_enabled=manifest['live_flashing_enabled'],
                 exact_reproduction=True,missing_profile_rejected=True),
        final_bounds=dict(payload_bytes=payload,rounded_payload_bytes=(payload+4095)&~4095,staging_capacity=0x25e000,
                          staging_headroom=0x25e000-payload,app_raw_bytes=raw,app_allocation=0x200000,app_headroom=0x200000-raw),
        maximum_profile_bounds=dict(runtime_bytes=98304,physical_start='0x0039bea0',physical_end='0x003b3ea0',
                                    erase_end='0x003b4000',allocation_end='0x003eb000',remaining_raw=225632,remaining_after_erase=225280),
        tests=dict(python_groups=sum(logs.values()),logs=logs,real_link_boundaries=[65536,65552,98304,98320],
                   rv32_gate_cases=7955,native_and_C_gate_targets_mocked=True),
        unchanged_guards=dict(entry='0x0439bea0',display_gate='0x0439bee0',static_function_frame_max=512,
                              no_writable_sections=True,no_relocations=True,no_imports=True,single_rx_segment=True),
        changed_source_sha256={p:sha((ROOT/p).read_bytes()) for p in changed},build_source_sha256=build['source_sha256'],
        limitations=['The current runtime remains 65456 bytes; only synthetic link/OTA fixtures exercise lengths above64KiB.',
                     'Every future executable and compressed OTA must pass all per-image checks; no arbitrary limit or manifest grants authority.',
                     'This uses unused existing application allocation, not reclaimed stock dashboard code/assets or RAM.',
                     'Stock dashboard replacement/reclamation remains a separate authorized future workstream, not a compatibility requirement here.',
                     'No device operation, new hardware execution claim, live flasher admission or catalog change.',
                     'Per-function512B frame checks do not prove cumulative task stack safety.'])
    out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(passed=True,report=str(out),runtime_sha256=sha(blob),ota_sha256=sha(image))))
if __name__=='__main__': main()
