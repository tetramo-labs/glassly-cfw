"""Execute button probe plus stock GPIO, event dequeue, startup, pools and IPC.

Offline synthetic MMIO. Only OEM report generation and connect power/indicator
side effects are stubbed; the probe, GPIO reader, FIFO, timers and IPC are real.
ACK bitmap changes model radio completion; no radio or interrupts are emulated.
"""
import itertools
import json
import random
import struct
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE, UC_HOOK_MEM_READ
from unicorn.arm_const import *
from build_buttons_probe import build, STATE, STATE_BYTES, HOOKS
from build_notify_probe import TAIL
from inspect_notify_probe import machine
from firmware_image import ROOT, load_stock, sha256
from emulate_stock import call, gpio, BASE, STOP
from memory_layout import POOLS
from startup import reconstruct


def verify():
    package, payload, report = build()
    stock = load_stock()[2][1]
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    def target(offset):
        ins = next(md.disasm(payload[offset:offset+4], BASE+offset))
        assert ins.mnemonic == 'bl'
        return int(ins.op_str[1:], 16)
    poll, idle = target(0x3e28), target(0x3e36)
    # All raw word windows, including unaligned ones, not only literal alignment.
    owners = [i for i in range(len(stock)-3) if 0x22514 <= struct.unpack_from('<I',stock,i)[0] < 0x2276c]
    assert owners == [], owners
    bases = [i for i in range(len(stock)-3) if stock[i:i+4] == struct.pack('<I',0x22064)]
    assert bases == [0xbc1c]
    for offset in range(0,0xda00,2):
        ins = next(md.disasm(stock[offset:offset+4],BASE+offset),None)
        if ins and ins.mnemonic.startswith('b') and ins.op_str.startswith('#0x'):
            assert not BASE+TAIL <= int(ins.op_str[1:],16) < BASE+len(stock)
    uc = machine(payload)
    reads = []
    hook = uc.hook_add(UC_HOOK_MEM_READ, lambda u,a,p,s,v,d: reads.append(p),
                       begin=BASE+TAIL, end=BASE+len(payload)-1)
    uc.mem_write(STATE, b'\xa5'*600)
    uc.emu_start(BASE+0x201,BASE+0xcf48,count=500000)
    assert uc.reg_read(UC_ARM_REG_PC) == BASE+0xcf48
    assert not reads
    for address,data in reconstruct(stock)[1].items():
        assert bytes(uc.mem_read(address,len(data))) == data
    uc.hook_del(hook)
    # Actual initializer must leave the entire reserved block untouched.
    uc.mem_write(STATE,b'\xa5'*600)
    call(uc,0x1023bb4)
    assert bytes(uc.mem_read(STATE,600)) == b'\xa5'*600
    for head,start,count,stride in POOLS:
        if head == 0x206e0: count = 2
        cursor = int.from_bytes(uc.mem_read(head,4),'little')
        for expected in reversed([start+i*stride for i in range(count)]):
            assert cursor == expected
            cursor = int.from_bytes(uc.mem_read(cursor,4),'little')
        assert cursor == 0
    # Zero startup state, then initialize normal synthetic test environment.
    uc = machine(payload)
    uc.mem_map(0xf8000,0x10000)
    input_calls, min_sp = [], [0x2ff00]
    radio_writes, state_writes = [], set()
    def code(emu,address,size,_):
        min_sp[0] = min(min_sp[0],emu.reg_read(UC_ARM_REG_SP))
        if address == 0x101ca40:
            input_calls.append(emu.reg_read(UC_ARM_REG_R0))
            emu.reg_write(UC_ARM_REG_R0,0x55)
            emu.reg_write(UC_ARM_REG_PC,emu.reg_read(UC_ARM_REG_LR))
        elif address == 0x101c874:
            emu.reg_write(UC_ARM_REG_PC,emu.reg_read(UC_ARM_REG_LR))
    def write(emu,access,address,size,value,_):
        if 0xc0000 <= address < 0xd0000:
            assert 0xc6000 <= address < 0xc6020
            assert emu.reg_read(UC_ARM_REG_PRIMASK) == 1
            radio_writes.append(address)
        if STATE <= address < STATE+600:
            assert address+size <= STATE+STATE_BYTES
            state_writes.update(range(address,address+size))
    uc.hook_add(UC_HOOK_CODE,code)
    uc.hook_add(UC_HOOK_MEM_WRITE,write)
    def event(opcode,value=b''):
        packet = bytes([2,opcode,len(value)])+value
        uc.mem_write(0x25000,packet)
        uc.mem_write(0x20f8c,struct.pack('<5I',0x25000,512,len(packet),0,len(packet)))
        uc.mem_write(0x20020,struct.pack('<I',1))
        call(uc,0x101986c)
        assert int.from_bytes(uc.mem_read(0x20f94,4),'little') == 0
    def start():
        uc.mem_write(0x20682,b'\x02')
        event(8,b'\x45\x23\xa1')
        assert uc.mem_read(STATE+8,1) == b'\x01'
    def sample(bits,read=0,cursor=0,sleep=0,mask=0,ack=False):
        expected = gpio(uc,bits)
        uc.mem_write(0x24000,struct.pack('<4H',0x6000,0x601f,0x6000+read,0x6000+cursor))
        uc.mem_write(0xc6000,b'\xa5'*32)
        uc.mem_write(0x20038,bytes([sleep]))
        uc.mem_write(0x20010,struct.pack('<I',0x80000001|(64 if ack else 0)))
        uc.reg_write(UC_ARM_REG_PRIMASK,mask)
        saved = (UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7)
        for i,r in enumerate(saved): uc.reg_write(r,0x554400+i)
        radio_writes.clear()
        assert call(uc,poll,0x12345678) == 0x55
        assert input_calls[-1] == 0x12345678
        assert uc.reg_read(UC_ARM_REG_PRIMASK) == mask
        for i,r in enumerate(saved): assert uc.reg_read(r) == 0x554400+i
        end = int.from_bytes(uc.mem_read(0x24006,2),'little')-0x6000
        sent = (end-cursor)%32
        assert sent in (0,13)
        data = bytes(uc.mem_read(0xc6000,32))
        assert bool(radio_writes) == bool(sent)
        packet = bytes(data[(cursor+i)%32] for i in range(sent))
        unchanged = set(range(32))-{(cursor+i)%32 for i in range(sent)}
        assert all(data[i] == 0xa5 for i in unchanged)
        assert int.from_bytes(uc.mem_read(0x20010,4),'little') & ~64 == 0x80000001
        return expected,packet
    # Real full dispatcher validates handle + exact control lengths.
    start()
    for value in (b'',b'\x45',b'\x45\x23',b'\x46\x23\xa0',b'\x45\x23\x31',b'\x45\x23\xa0\x00'):
        event(8,value)
        assert uc.mem_read(STATE+8,1) == b'\x01'
    event(8,b'\x45\x23\xa0')
    assert sample(4095)[1] == b''
    for bits in range(4096):
        start()
        expected,packet = sample(bits)
        if bits: assert not packet
        expected,packet2 = sample(bits)
        actual = packet or packet2
        assert actual == b'\x01\x09\x0a\x45\x23\x47\x04\x00\x02'+struct.pack('<I',expected)
    cases = 0
    for read,cursor,mask in itertools.product(range(32),range(32),(0,1)):
        start()
        _,packet = sample(0,read,cursor,mask=mask,ack=True)
        assert bool(packet) == (((read-cursor)%32 or 32)>13)
        cases += 1
    for sleep in (1,2,255):
        start()
        assert not sample(0,sleep=sleep)[1]
        assert uc.mem_read(STATE+5,1) == b'\x01'
        assert sample(0)[1]
    # Independent Python state machine under random bounce, congestion, ACKs,
    # sleeping radio, overflow and both incoming interrupt masks.
    rng = random.Random(0x8b17)
    start()
    candidate=stable=seq=head=flags_pending=0
    initialized=pending=False
    queue=[];flags=2;overflows=sent_total=0
    for i in range(12000):
        bits = rng.randrange(4096) if i%3==0 else bits
        read,cursor = rng.randrange(32),rng.randrange(32)
        sleep = 1 if rng.randrange(10)==0 else 0
        ack = rng.randrange(8)==0
        mask = rng.randrange(2)
        raw,packet = sample(bits,read,cursor,sleep,mask,ack)
        if raw == candidate and (not initialized or raw != stable):
            stable=raw;initialized=True
            if len(queue)==16:
                queue=[];head=0;flags|=1;overflows+=1
            queue.append(raw)
        candidate=raw
        if pending and ack: pending=False;seq=(seq+1)%256
        wanted=b''
        if queue and not pending and not sleep and ((read-cursor)%32 or 32)>13:
            raw_sent=queue.pop(0)
            wanted=b'\x01\x09\x0a\x45\x23\x47\x04'+bytes([seq,flags])+struct.pack('<I',raw_sent)
            head=(head+1)%16;flags=0;pending=True;sent_total+=1
        assert packet == wanted,(i,packet.hex(),wanted.hex())
        state=bytes(uc.mem_read(STATE,STATE_BYTES))
        assert struct.unpack_from('<HH',state) == (candidate,stable)
        assert list(state[4:11]) == [head,len(queue),seq,flags,1,int(pending),int(initialized)]
        stored=[struct.unpack_from('<H',state,12+2*((head+j)%16))[0] for j in range(len(queue))]
        assert stored == queue
        if wanted: assert state[44:48] == wanted[7:11]
    assert overflows>0 and sent_total>256
    # Reconnect resets even without an intervening poll in disconnected state.
    event(2)
    assert bytes(uc.mem_read(STATE,12)) == bytes(12)
    assert not sample(1)[1]
    start();sample(0)
    uc.mem_write(0x20682,b'\x03')
    assert not sample(4095)[1]
    assert bytes(uc.mem_read(STATE,12)) == bytes(12)
    idle_cases=[]
    for state in (0,1,2,3):
        call(uc,0x1023a5c)
        uc.mem_write(0x20682,bytes([state]))
        uc.mem_write(0x20198,struct.pack('<I',123))
        call(uc,idle)
        count=int.from_bytes(uc.mem_read(0x20198,4),'little')
        assert count == (0 if state==2 else 124)
        assert bool(uc.mem_read(0x21ed0,1)[0]) == (state!=2)
        idle_cases.append(state)
    return dict(kind='Offline button streaming execution and independent queue model',hardware_accessed=False,
                package_sha256=sha256(package),plaintext_sha256=sha256(payload),
                source_sha256=sha256((ROOT/'firmware/buttons_probe.s').read_bytes()),
                gpio_combinations=4096,ipc_capacity_irq_cases=cases,random_model_polls=12000,
                model_overflows=overflows,model_packets=sent_total,
                startup_matches_stock=True,startup_reads_tail=False,pool_block_reserved=True,
                oem_pool_counts=[2,4,4,3,1,3,5,3],reserved_block_pointer_candidates=owners,
                sole_pool_base_pointer_offset=hex(bases[0]),state_written_extent=[hex(min(state_writes)),hex(max(state_writes)+1)],
                poll_entry=hex(poll),idle_entry=hex(idle),idle_states=idle_cases,
                maximum_observed_stack_bytes=0x2ff00-min_sp[0],
                stubs={'0x0101ca40':'OEM report task returns 0x55; argument and saved registers checked',
                       '0x0101c874':'OEM connection power/indicator helper only'},
                limits=['No radio, interrupt execution, actual sampling cadence or physical button labels',
                        'ACK bits are synthetic; no new proof of radio FIFO errors or CCC ordering',
                        'No complete stack/ROM/DMA ownership claim; static word scan cannot exclude computed accesses',
                        'Reduced OEM allocation capacity needs live coexistence testing'])


if __name__=='__main__':
    result=verify()
    (ROOT/'build/buttons-probe/emulation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
