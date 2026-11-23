#!/usr/bin/env python3
"""Cold-boot minimal launcher: preserve descriptor identity and shared screen.

Adds fixed callback substitutions and two original-entry tail jumps to the
reviewed owner-disabled/registry-carved image. No old launcher bytes are reused.
The runtime and all build inputs must match their build report. Live admission
still requires a separately pinned Swift catalog entry and execution evidence.
"""
import argparse,json,struct
from pathlib import Path
from build_memomind_flash_canary import construct_canary
from build_memomind_dashboard_ram import apply_ram_gates
from build_memomind_graphics import BODY_BASE,ENTRY,_guard_final_bounds
from memomind_rx_profile import DEFAULT_RX_PROFILE
from memomind_ota import require,sha,repack,unpack_ota
ROOT=Path(__file__).resolve().parents[1]
CALLBACKS=((0x0439a394,0x04273454,'init'),(0x0439a39c,0x04271d6a,'destroy'),
           (0x0439a3ac,0x04273266,'tick'),(0x0439a3b4,0x04272a36,'event'),
           (0x0439a3b8,0x04273734,'message'))
BOUNDARIES=((0x0427253a,'411122c426c206c6','home'),(0x04272960,'411122c600083244','suspend'))
def apply_first_run_gate(body):
    address=0x0425bf50;off=address-BODY_BASE
    before=bytes.fromhex('130549cf');after=bytes.fromhex('1385c4c7')
    require(body[off:off+4]==before,'First-run app selection witness differs')
    body[off:off+4]=after
    return dict(address=address,before=before.hex(),after=after.hex(),purpose='first-run-minimal-launcher')
def jump(address):
    require(ENTRY<=address<ENTRY+98304 and not address%2,'Invalid runtime callback')
    hi=(address+0x800)>>12;lo=address-(hi<<12)
    return struct.pack('<II',(hi<<12)|(5<<7)|0x37,((lo&4095)<<20)|(5<<15)|0x67)
def jal(address,target):
    delta=target-address;require(-(1<<20)<=delta<(1<<20) and delta%2==0,'JAL range')
    ins=((delta>>20&1)<<31)|((delta>>1&1023)<<21)|((delta>>11&1)<<20)|((delta>>12&255)<<12)|(1<<7)|0x6f
    return struct.pack('<I',ins)
BLE_ADV_STOP_SITES=(0x042e0ff6,0x042e1020,0x042e2062,0x042df852,0x042d5b56)
def apply_ble_link(body,symbols,blob_bytes):
    def target(name):
        address=symbols[name];require(ENTRY<=address<ENTRY+blob_bytes and address%2==0,name+' outside runtime')
        return address
    edits=[]
    def patch(address,before,after,purpose):
        off=address-BODY_BASE;require(body[off:off+len(before)]==before,purpose+' witness differs')
        body[off:off+len(after)]=after
        edits.append(dict(address=address,before=before.hex(),after=after.hex(),purpose=purpose))
    patch(0x042db006,bytes.fromhex('397122dc4ad852d4'),jump(target('glassly_gm_write_entry')),'ble-gm-writer')
    patch(0x0435d978,struct.pack('<I',0x04240430),struct.pack('<I',target('glassly_ota_ble_send')),'ble-ota-send')
    stop=target('glassly_adv_stop')
    for address in BLE_ADV_STOP_SITES:
        patch(address,jal(address,0x042d556a),jal(address,stop),'ble-adv-stop')
    return edits
def construct(source,blob,build):
    require(build.get('minimal_launcher') and build.get('diagnostic_commands') and build.get('reset_undo_trim'),'Requires minimal launcher diagnostic profile')
    require(sha(blob)==build['blob_sha256'] and len(blob)==build['blob_bytes'],'Runtime pin mismatch')
    for p,h in build['source_sha256'].items():require(sha((ROOT/p).read_bytes())==h,'Build source changed: '+p)
    revision=build.get('cfw_revision',1)
    require(type(revision) is int and 1<=revision<=65535,'Invalid CFW revision')
    version='GLASSLYCFW/'+str(revision)
    require(('\"version\":\"'+version+'\"').encode() in blob,'Version differs from runtime')
    profile=build.get('rx_profile',DEFAULT_RX_PROFILE)
    base,base_manifest,base_proof=construct_canary(source,blob,rx_profile=profile)
    _,old=unpack_ota(base);original=old[3]['raw'][32:];body,gates=apply_ram_gates(original);body=bytearray(body);edits=[]
    if revision>=11:
        edits.append(apply_first_run_gate(body))
    for address,before,name in CALLBACKS:
        off=address-BODY_BASE;target=build['symbols']['glassly_launcher_'+name+'_entry']
        require(body[off:off+4]==struct.pack('<I',before),'Callback witness differs')
        require(ENTRY<=target<ENTRY+len(blob) and target%2==0,'Callback outside runtime')
        after=struct.pack('<I',target);body[off:off+4]=after
        edits.append(dict(address=address,before=struct.pack('<I',before).hex(),after=after.hex(),purpose=name))
    for address,before,name in BOUNDARIES:
        off=address-BODY_BASE;target=build['symbols']['glassly_launcher_'+name+'_entry']
        require(body[off:off+8]==bytes.fromhex(before),'External entry witness differs')
        after=jump(target);body[off:off+8]=after
        edits.append(dict(address=address,before=before,after=after.hex(),purpose=name))
    if build.get('notification_relay'):
        address=0x04273ee6;before=bytes.fromhex('ed77aa97c207c183')
        off=address-BODY_BASE
        require(body[off:off+8]==before,'Calibration presentation entry witness differs')
        after=bytes.fromhex('1305000067800000')
        body[off:off+8]=after
        edits.append(dict(address=address,before=before.hex(),after=after.hex(),purpose='suppress-calibration-presentation'))
        address=0x0421d17c;before=bytes.fromhex('797122d426d206d6')
        off=address-BODY_BASE
        require(body[off:off+8]==before,'Vendor app-launch entry witness differs')
        after=bytes.fromhex('1305000067800000')
        body[off:off+8]=after
        edits.append(dict(address=address,before=before.hex(),after=after.hex(),purpose='suppress-vendor-app-launch'))
        address=0x04217568;before=bytes.fromhex('97201000e780a022')
        off=address-BODY_BASE;target=build['symbols']['glassly_notification_entry']
        require(ENTRY<=target<ENTRY+len(blob) and target%2==0,'ANCS hook outside runtime')
        require(body[off:off+8]==before,'ANCS pre-stock witness differs')
        # AUIPC/JALR call: preserve ra=04217570 for the original continuation.
        delta=target-address;hi=(delta+0x800)>>12;lo=delta-(hi<<12)
        after=struct.pack('<II',((hi&0xfffff)<<12)|(1<<7)|0x17,((lo&4095)<<20)|(1<<15)|(1<<7)|0x67)
        body[off:off+8]=after
        edits.append(dict(address=address,before=before.hex(),after=after.hex(),purpose='ancs-prestock'))
    if build.get('microphone_control'):
        require(revision>=7 and build.get('wake_control'),'Invalid microphone profile')
        target=build['symbols']['glassly_microphone_task_entry']
        require(ENTRY<=target<ENTRY+len(blob) and target%2==0,'Microphone callback outside runtime')
        hi=(target+0x800)>>12;lo=target-(hi<<12)
        callback=((0x0420980c,'b7a52004',struct.pack('<I',(hi<<12)|(11<<7)|0x37)),
                  (0x04209814,'93856531',struct.pack('<I',((lo&4095)<<20)|(11<<15)|(11<<7)|0x13)))
        for address,before,after in callback:
            off=address-BODY_BASE
            require(body[off:off+4]==bytes.fromhex(before),'Microphone registration witness differs')
            body[off:off+4]=after
            edits.append(dict(address=address,before=before,after=after.hex(),purpose='microphone-task-registration'))
        hooks=((0x0431ca9e,'1d7186cea2cca6ca','spp'),(0x0431b88c,'797106d622d426d2','iap2'),
               (0x04245cf4,'011126cab7440102','link'))
        for address,before,name in hooks:
            off=address-BODY_BASE;target=build['symbols']['glassly_microphone_'+name+'_entry']
            require(body[off:off+8]==bytes.fromhex(before),'Microphone hook witness differs')
            after=jump(target);body[off:off+8]=after
            edits.append(dict(address=address,before=before,after=after.hex(),purpose='microphone-'+name))
    if build.get('sensor_capture'):
        require(revision>=8 and build.get('microphone_control'),'Invalid sensor profile')
        address=0x0422b67a;before='797122d44ad04ece';target=build['symbols']['glassly_sensor_als_entry']
        off=address-BODY_BASE;require(body[off:off+8]==bytes.fromhex(before),'ALS entry witness differs')
        after=jump(target);body[off:off+8]=after
        edits.append(dict(address=address,before=before,after=after.hex(),purpose='sensor-als'))
        address=0x043475f6;before='eff09fe3';target=build['symbols']['glassly_sensor_imu_entry']
        require(ENTRY<=target<ENTRY+len(blob) and target%2==0,'IMU observer outside runtime')
        off=address-BODY_BASE;require(body[off:off+4]==bytes.fromhex(before),'IMU read call witness differs')
        delta=target-address;require(-(1<<20)<=delta<(1<<20) and delta%2==0,'IMU JAL range')
        ins=((delta>>20&1)<<31)|((delta>>1&1023)<<21)|((delta>>11&1)<<20)|((delta>>12&255)<<12)|(1<<7)|0x6f
        after=struct.pack('<I',ins);body[off:off+4]=after
        edits.append(dict(address=address,before=before,after=after.hex(),purpose='sensor-imu'))
    if build.get('ble_probe') and 'glassly_ble_boot_entry' in build['symbols']:
        address=0x042db6e8;before='efa04f9e';target=build['symbols']['glassly_ble_boot_entry']
        require(ENTRY<=target<ENTRY+len(blob) and target%2==0,'BLE boot entry outside runtime')
        off=address-BODY_BASE;require(body[off:off+4]==bytes.fromhex(before),'BLE init call witness differs')
        delta=target-address;require(-(1<<20)<=delta<(1<<20) and delta%2==0,'BLE JAL range')
        ins=((delta>>20&1)<<31)|((delta>>1&1023)<<21)|((delta>>11&1)<<20)|((delta>>12&255)<<12)|(1<<7)|0x6f
        after=struct.pack('<I',ins);body[off:off+4]=after
        edits.append(dict(address=address,before=before,after=after.hex(),purpose='ble-boot-register'))
    if build.get('ble_probe') and revision>=25:
        edits+=apply_ble_link(body,build['symbols'],len(blob))
    allowed={i for row in gates+edits for i in range(row['address']-BODY_BASE,row['address']-BODY_BASE+len(bytes.fromhex(row['after'])))}
    changed=[i for i,(a,b) in enumerate(zip(original,body)) if a!=b]
    require(set(changed)<=allowed and len(body)==len(original),'Change outside fixed lifecycle gates')
    image=repack(base,{3:bytes(body)});_guard_final_bounds(len(image),len(body)+32)
    decoded,final=unpack_ota(image);require(final[3]['raw'][32:]==body,'Reconstructed body differs')
    for i in (0,1,2,4,5,6):require(final[i]['packed']==old[i]['packed'],'Unrelated component changed')
    return image,dict(format='memomind-minimal-owner-v1',version=version,cold_boot_required=True,
        output_sha256=sha(image),output_bytes=len(image),blob_sha256=sha(blob),blob_bytes=len(blob),
        source_sha256=sha(source),rx_profile=profile,flash_scene=build.get('flash_scene',False),
        launcher_edits=edits,dashboard_gates=gates,base_manifest=base_manifest,
        proof=dict(changed_offsets=changed,unchanged_components=[0,1,2,4,5,6],checksums=decoded['checksums'],base=base_proof),
        hardware_validated=False,old_launcher_flash_reused=False,heap_saving_measured=False)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('build',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    image,manifest=construct(a.source.read_bytes(),(a.build/'graphics.bin').read_bytes(),json.loads((a.build/'build.json').read_text()))
    a.output.mkdir(parents=True,exist_ok=False);(a.output/'firmware.bin').write_bytes(image)
    (a.output/'expected-app-header.bin').write_bytes(unpack_ota(image)[1][3]['raw'][:256])
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({k:manifest[k] for k in ('output_sha256','output_bytes','blob_sha256','blob_bytes')}))
if __name__=='__main__':main()
