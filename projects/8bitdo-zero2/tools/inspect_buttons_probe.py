"""Execute button probe plus stock GPIO, event dequeue, startup, pools and IPC.

Offline synthetic MMIO. Only OEM report generation and connect power/indicator
side effects are stubbed; the probe, GPIO reader, FIFO, timers and IPC are real.
ACK bitmap changes model radio completion; no radio or interrupts are emulated.
The LED checks run the stock LED engine, dispatcher, connect helper and pairing
entry; only that entry's command-02 submission is skipped.
"""
import itertools
import json
import random
import struct
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE, UC_HOOK_MEM_READ
from unicorn.arm_const import *
from build_buttons_probe import build, STATE, STATE_BYTES, HOOKS, LED_HOOKS
from build_notify_probe import TAIL
from inspect_notify_probe import machine
from firmware_image import ROOT, load_stock, sha256
from emulate_stock import call, gpio, BASE, STOP
from memory_layout import POOLS
from startup import reconstruct


# LED driver 0x010232bc: mask bit 0 -> GPIO0.3, bit 1 -> GPIO0.2, bit 2 -> GPIO2.3.
LED_PINS = (0xf8703, 0xf8702, 0xf8723)
LED_RAM = (0x206b0, 0x206e0)
LED_START, LED_TICK, LED_SELECT = 0x10247c4, 0x1024585, 0x10242f0
PAIRING_ENTRY, VISIBILITY = 0x101b5d8, 0x101a304
CONTROL_HANDLE = b'\x45\x23'


def led_machine(payload, pairing=False):
    uc = machine(payload)
    uc.mem_map(0xf0000, 0x10000)
    uc.mem_write(0xf873c, struct.pack('<3H', 0xffff, 0xffbf, 0xffff))
    call(uc, LED_START)
    if pairing:
        # Real pairing entry; only its command-02 submission, which waits for a
        # radio acknowledgement, returns immediately.
        skip = uc.hook_add(UC_HOOK_CODE, lambda e,a,s,d: e.reg_write(UC_ARM_REG_PC, e.reg_read(UC_ARM_REG_LR)),
                           begin=VISIBILITY, end=VISIBILITY)
        call(uc, PAIRING_ENTRY, limit=500000)
        uc.hook_del(skip)
        assert uc.mem_read(0x201dc, 1)[0] == 0x40
    return uc


def led_output(uc):
    return tuple(int(uc.mem_read(a, 1)[0] & 0x3f == 0x3f) for a in LED_PINS)


def led_ticks(uc, count):
    sequence = []
    for _ in range(count):
        assert int.from_bytes(uc.mem_read(0x206b8, 4), 'little') == LED_TICK
        call(uc, LED_TICK & ~1, limit=200000)
        sequence.append(led_output(uc))
    return sequence


def led_event(uc, opcode, value=b''):
    packet = bytes([2, opcode, len(value)]) + value
    uc.mem_write(0x25000, packet)
    uc.mem_write(0x20f8c, struct.pack('<5I', 0x25000, 512, len(packet), 0, len(packet)))
    uc.mem_write(0x20020, struct.pack('<I', 1))
    call(uc, 0x101986c, limit=200000)
    assert int.from_bytes(uc.mem_read(0x20f94, 4), 'little') == 0


def led_inputs(uc, status=0, hid=0, ble=0, level=0, b2=0, b3=0, colour=0, link=0, mode=6):
    uc.mem_write(0x201dc, bytes([status]))
    uc.mem_write(0x20182, bytes([hid]))
    uc.mem_write(0x20682, bytes([ble]))
    uc.mem_write(0xf873e, struct.pack('<H', 0xffbf | (0x40 if level else 0)))
    uc.mem_write(0x206b2, bytes([b2, b3]))
    uc.mem_write(0x20158, bytes([colour]))
    uc.mem_write(0x20181, bytes([link]))
    uc.mem_write(0x201b4, bytes([mode]))


def blinking(sequence):
    return any(sequence) and len(set(sequence)) > 1


def verify_led(payload, stock):
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    entries = {}
    for offset in LED_HOOKS:
        ins = next(md.disasm(payload[offset:offset+4], BASE+offset))
        assert ins.mnemonic == 'bl'
        entries[offset] = int(ins.op_str[1:], 16)
        assert BASE+TAIL <= entries[offset] < BASE+len(payload)
    assert entries[0xc5ee] == entries[0xc62e] and len(set(entries.values())) == 3
    # No stock branch may land inside a replaced two-instruction pair.
    interiors = {BASE+offset+2 for offset in HOOKS if len(HOOKS[offset]) == 4}
    for offset in range(0, 0xda00, 2):
        ins = next(md.disasm(stock[offset:offset+4], BASE+offset), None)
        if ins and ins.mnemonic.startswith('b') and ins.op_str.startswith('#0x'):
            assert int(ins.op_str[1:], 16) not in interiors

    # For reconnect and pairing modes: stock keeps blinking after BLE event 02;
    # stock HID connect (dispatcher case 0xb7) is solid; patched BLE connect gives
    # that output from the first tick, A1/A0 keep it, event 05 restores stock.
    scenarios = {}
    for pairing in (False, True):
        reference = led_machine(stock, pairing)
        before = led_ticks(reference, 400)
        led_event(reference, 2)
        assert reference.mem_read(0x20682, 1)[0] == 2 and reference.mem_read(0x20182, 1)[0] != 2
        stock_linked = led_ticks(reference, 400)
        assert blinking(before) and blinking(stock_linked)
        reference = led_machine(stock, pairing)
        led_ticks(reference, 123)
        led_event(reference, 0xb7)
        assert reference.mem_read(0x20182, 1)[0] == 2 and reference.mem_read(0x201dc, 1)[0] == 0
        stock_hid = led_ticks(reference, 400)
        assert len(set(stock_hid)) == 1 and any(stock_hid[0])

        uc = led_machine(payload, pairing)
        assert led_ticks(uc, 400) == before
        led_event(uc, 2)
        connected = led_ticks(uc, 400)
        assert connected == stock_hid
        led_event(uc, 8, CONTROL_HANDLE + b'\xa1')
        assert uc.mem_read(STATE+8, 1) == b'\x01'
        connected += led_ticks(uc, 200)
        led_event(uc, 8, CONTROL_HANDLE + b'\xa0')
        assert uc.mem_read(STATE+8, 1) == b'\x00'
        connected += led_ticks(uc, 200)
        assert set(connected) == {stock_hid[0]}
        assert uc.mem_read(0x201dc, 1)[0] == (0x40 if pairing else 0)
        led_event(uc, 5)
        assert uc.mem_read(0x20682, 1)[0] == 3
        assert led_ticks(uc, 400) == before
        led_event(uc, 2)
        assert led_ticks(uc, 1) == [stock_hid[0]]
        scenarios['pairing' if pairing else 'reconnect'] = dict(
            stock_changes_in_400_ticks_after_event02=sum(a != b for a, b in zip(stock_linked, stock_linked[1:])),
            stock_hid_connect_output=list(stock_hid[0]), patched_event02_output=list(connected[0]))

    # Selector equivalence: patched(state) == stock(state as left by HID connect:
    # HID 2 and pairing flag clear) whenever BLE is 2, and == stock otherwise.
    patched_uc, stock_uc = led_machine(payload), led_machine(stock)
    def select(emu, inputs):
        emu.mem_write(LED_RAM[0], b'\x00'*(LED_RAM[1]-LED_RAM[0]))
        emu.mem_write(0x20194, b'\x00'*4)
        for address in LED_PINS:
            emu.mem_write(address, b'\x3e')
        led_inputs(emu, **inputs)
        emu.mem_write(0x206b1, bytes([inputs['level']]))
        call(emu, LED_SELECT)
        return (bytes(emu.mem_read(LED_RAM[0], LED_RAM[1]-LED_RAM[0])),
                bytes(emu.mem_read(0x20194, 4)), led_output(emu))
    selector_cases = changed_cases = 0
    for status, hid, ble, level, b2, b3, colour, link, mode in itertools.product(
            (0, 0x40), range(4), (0, 2, 3), (0, 1), (0, 1), (0, 1), (0, 1), range(4), (0, 1, 2, 3, 4, 6)):
        inputs = dict(status=status, hid=hid, ble=ble, level=level, b2=b2, b3=b3,
                      colour=colour, link=link, mode=mode)
        expected = dict(inputs, hid=2, status=0) if ble == 2 else inputs
        patched = select(patched_uc, inputs)
        assert patched == select(stock_uc, expected), inputs
        if patched != select(stock_uc, inputs):
            assert ble == 2 and (hid != 2 or status), inputs
            changed_cases += 1
        selector_cases += 1
    assert changed_cases

    # Lock-step ticks with random inputs. Without a BLE link every written byte
    # matches stock; with a link only the two snapshot bytes differ.
    rng = random.Random(0x1ed)
    tick_cases = 0
    for linked in (False, True):
        new_uc, old_uc = led_machine(payload), led_machine(stock)
        writes = (set(), set())
        def record(emu, access, address, size, value, written):
            if address < 0x2f000:
                written.update(range(address, address+size))
        for emu, written in zip((new_uc, old_uc), writes):
            emu.hook_add(UC_HOOK_MEM_WRITE, record, user_data=written)
        hid = 0
        for i in range(3000):
            if i % 97 == 0:
                inputs = dict(level=rng.randrange(2), b2=rng.randrange(2), b3=rng.randrange(2),
                              colour=rng.randrange(2), link=rng.randrange(4), mode=rng.choice((0, 1, 2, 3, 4, 6)))
                status = rng.choice((0, 0x40))
                if not linked:
                    hid = rng.randrange(4)
                led_inputs(new_uc, status=status, hid=hid, ble=2 if linked else rng.choice((0, 3)), **inputs)
                led_inputs(old_uc, status=0 if linked else status, hid=2 if linked else hid, **inputs)
            assert led_ticks(new_uc, 1) == led_ticks(old_uc, 1), (linked, i)
            ram = [bytearray(e.mem_read(LED_RAM[0], LED_RAM[1]-LED_RAM[0])) for e in (new_uc, old_uc)]
            if linked:
                assert ram[0][0x206da-LED_RAM[0]] == 2 and ram[1][0x206da-LED_RAM[0]] == 0
                for r in ram:
                    r[0x206d9-LED_RAM[0]] = r[0x206da-LED_RAM[0]] = 0
            assert ram[0] == ram[1], (linked, i)
            tick_cases += 1
        assert writes[0] == writes[1]

    stack = {}
    for label, image, ble in (('stock', stock, 0), ('patched', payload, 2)):
        emu = led_machine(image)
        led_inputs(emu, ble=ble)
        lowest = [0x2ff00]
        emu.hook_add(UC_HOOK_CODE, lambda e,a,s,d: lowest.__setitem__(0, min(lowest[0], e.reg_read(UC_ARM_REG_SP))))
        led_ticks(emu, 300)
        stack[label] = 0x2ff00 - lowest[0]
    assert stack['patched'] - stack['stock'] <= 8

    return dict(led_driver='0x010232bc (mask bit0 GPIO0.3, bit1 GPIO0.2, bit2 GPIO2.3)',
                led_engine=dict(start=hex(LED_START), tick=hex(LED_TICK & ~1), selector=hex(LED_SELECT),
                                selector_pairing_test='0x01024304 calls 0x0101f080 (bit 6 of 0x000201dc)',
                                selector_connected_test='0x01024354 reads HID state 0x00020182 == 2',
                                snapshot_predicate_calls=['0x010245ee', '0x0102462e']),
                hook_targets={hex(k): hex(v) for k, v in entries.items()},
                scenarios=scenarios, patched_a1_a0_unchanged=True,
                patched_event05_restores_stock_sequence=True,
                selector_equivalence_cases=selector_cases, selector_cases_changed_by_ble_link=changed_cases,
                lockstep_ticks=tick_cases, ram_write_sets_match_stock=True,
                observed_led_tick_stack_bytes=stack,
                stubs={hex(VISIBILITY): 'command-02 visibility submission during pairing entry only'},
                limits=['Physical LED colour/pin population on the Zero 2 PCB is not established',
                        'No interrupt, timer cadence or radio execution; events are injected into the software ring',
                        'Not observed on hardware'])


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
    led = verify_led(payload, stock)
    return dict(kind='Offline button streaming execution and independent queue model',hardware_accessed=False,
                package_sha256=sha256(package),plaintext_sha256=sha256(payload),
                source_sha256=sha256((ROOT/'firmware/buttons_probe.s').read_bytes()),
                gpio_combinations=4096,ipc_capacity_irq_cases=cases,random_model_polls=12000,
                model_overflows=overflows,model_packets=sent_total,
                startup_matches_stock=True,startup_reads_tail=False,pool_block_reserved=True,
                oem_pool_counts=[2,4,4,3,1,3,5,3],reserved_block_pointer_candidates=owners,
                sole_pool_base_pointer_offset=hex(bases[0]),state_written_extent=[hex(min(state_writes)),hex(max(state_writes)+1)],
                poll_entry=hex(poll),idle_entry=hex(idle),idle_states=idle_cases,
                maximum_observed_stack_bytes=0x2ff00-min_sp[0],led=led,
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
