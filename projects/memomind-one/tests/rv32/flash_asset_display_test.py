#!/usr/bin/env python3
"""Check the hardware smoke's cached-font checkerboard through flash reads."""
import argparse, json, struct
from pathlib import Path
import graphics_runtime_emulator_test as G
import scene_runtime_emulator_test as S
from minimal_owner_flash_runtime_emulator_test import FlashMachine

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();G.BUILD=a.build.resolve()
    G.PINNED_SHA=json.loads((G.BUILD/'build.json').read_text())['blob_sha256']
    m=FlashMachine();m.send_scene(S.reset_packet())
    font=bytearray(898);struct.pack_into('<I',font,132,384)
    font[384:386]=bytes([64,64])
    for y in range(64):
        for x in range(8):font[386+y*8+x]=0x80 | (15 if (y//8+x)%2==0 else 0)
    put=struct.pack('<BHHBIIBIIH',37,m.epoch,2,0,5,1,1,len(font),0,len(font))+font
    reply,_=m.send_scene(put);assert reply[3]==0
    reads=m.io_calls
    _,values=m.send_scene(struct.pack('<BIhhBBB',20,5,20,140,15,1,65),patch_epoch=False)
    assert values[0]['result']=='ok' and m.io_calls>reads
    for y in range(64):
        for x in range(64):assert m.pixel(20+x,140+y)==(15 if (x//8+y//8)%2==0 else 0)
    m.call('glassly_launcher_destroy_entry',display=True)
    assert not (m.images or m.owned_live())
    a.report.write_text(json.dumps(dict(passed=True,runtime_sha256=G.PINNED_SHA,
        pixels_checked=4096,flash_calls_during_draw=m.io_calls-reads,
        hardware_tested=False,mock_boundaries=['Flash broker and physical I/O','LVGL scheduler/heap']),indent=2)+'\n')

if __name__=='__main__':main()
