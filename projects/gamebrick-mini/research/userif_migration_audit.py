"""Offline validation of the USERIF 0x38 -> 0x40 settings migration (docs/userif-migration.md).

Runs the Sep 2025 and Oct 2025 (= Glassly) applications' real settings-load path under a
taint-tracking P-code executor, with USERIF supplied from the saved dumps, the migrated
record or an erased sector. Reads files only; no USB IO. Prints JSON, exits 1 on a failed
expectation.
"""
import hashlib, json, re, struct, sys
from pathlib import Path
import pypcode
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'jl-misctools/firmware'))
from flash_layout import Layout
from gamebrick_flasher import oem_application

BASE = 0x1e00120
USERIF, SECTOR = 0x7d000, 0x1000
MAP_SIZE, MAPS = 0xc8, 6
SENTINEL = 0x0dead0
HEAP = 0x30000
TESTER = ROOT/'device-backup-20261113-tester/flash-pass1.bin'
UNIT1 = ROOT/'device-backup-20261022-233350/flash-pass1.bin'
SHA = {'tester': '4d6d248101d342755bf51c2b18d7f81dd1b6c0629a5f6516f9edab8d1845df89',
       'unit1': '9b7c57387ded72fadd162599cfb2b3797fb27e10759918d4e06f879740577cb3',
       'sep2025': 'e858401635ddbc953ef5f6bc5a6d17dff9635a7536bb0d7a91c8d7824ffb21af',
       'oct2025': '2fb44f4235bd4ed7183439f31ee2a31fb0052d19dd736e20d1d251fd5e1ff259',
       'glassly': '495ce9131d2cadebd558ec6d5ebfd51b6afa1ba957cba5c7f5dd331fcba9f432'}

# Per-build addresses. Oct/Glassly from the analysed image; Sep counterparts found by byte
# alignment of the two builds and confirmed by identical prologues (see noboot_audit.py).
BUILDS = {
 'oct2025': dict(m_storage=0x3020, size=0x40, listmap=0x25e0, init=0x1e0afd8, task_create=0x1e0bcac, pwm_table=0x1e2258c,
     task_entry=0x1e0ee68, check_map=0x1e06b06, read=0x1e0b12a, division=0x1e0b322, sync=0x1e074e8,
     sdfile=dict(fopen=0x1e1b982, fattr=0x1e1ba70, fsaddr=0x1e1baa6, erase=0x1e0136e, fseek=0x1e1baf4, fread=0x1e1bab6, fwrite=0x1e1bbca, fclose=0x1e1bb40),
     malloc=0x1e0483c, free=0x1e0484a, printf=(0x1e197d0,), gpio_read=(0x4b1a, 0x1e04124), delay=0x1e0aa68, battery_sample=0x1e0aa86),
 'sep2025': dict(m_storage=0x3724, size=0x38, listmap=0x2da0, init=0x1e0b012, task_create=0x1e0bc58, pwm_table=0x1e22574,
     task_entry=0x1e0eea4, check_map=0x1e06ba8, read=0x1e0b14e, division=0x1e0b330, sync=0x1e0754c,
     sdfile=dict(fopen=0x1e1b98c, fattr=0x1e1ba7a, fsaddr=0x1e1bab0, erase=0x1e01374, fseek=0x1e1bafe, fread=0x1e1bac0, fwrite=0x1e1bbd4, fclose=0x1e1bb4a),
     malloc=0x1e048ee, free=0x1e048fc, printf=(0x1e197d8,), gpio_read=(0x4b1a, 0x1e041e0), delay=0x1e0aaa2, battery_sample=0x1e0aac0),
}
BUILDS['glassly'] = BUILDS['oct2025']
ROM = {0x106ee4: 'memcpy', 0x106eec: 'memcmp', 0x106ef0: 'memset', 0x106efc: 'strlen'}

arch = pypcode.Arch('Jieli', str(ROOT/'q32s-analysis/processor/data/languages/JieLi.ldefs'))
ctx = pypcode.Context(next(x for x in arch.languages if x.id == 'q32s:LE:32:default'))
REGS = ctx.registers
failures = []

def check(ok, message):
    if not ok: failures.append(message)
    return bool(ok)
def digest(data): return hashlib.sha256(data).hexdigest()

def modbus(data, crc=0xffff):
    for b in data:
        crc ^= b
        for _ in range(8): crc = (crc >> 1) ^ 0xa001 if crc & 1 else crc >> 1
    return crc

def maps_at(sector, start):
    """Classify each list map region: 'valid' (CRC-valid header), 'erased' or 'invalid'."""
    out = []
    for i in range(MAPS):
        o = start + i*MAP_SIZE; region = sector[o:o+MAP_SIZE]
        crc, res, mx, ml = struct.unpack_from('<HHHH', region)
        if region == b'\xff'*MAP_SIZE: out.append('erased')
        # Accepted by both builds: Sep needs 8 <= len <= 0xc0 (0x1e06bba), Oct needs len % 4 == 0 (0x1e06b26).
        elif mx == MAP_SIZE and 8 <= ml <= MAP_SIZE-8 and ml % 4 == 0 and modbus(region[2:8+ml]) == crc: out.append('valid')
        else: out.append('invalid')
    return out

def migration_preconditions(sector):
    """The coordinator's checks before migrating, plus the ones this audit adds."""
    problems = []
    if sector[0x0e:0x20] != b'\xff'*0x12: problems.append('old[0x0e:0x20] not erased')
    if sector[SECTOR-8:SECTOR] != b'\xff'*8: problems.append('old[0xff8:0x1000] not erased')
    kinds = maps_at(sector, 0x38)
    if any(k == 'invalid' for k in kinds): problems.append(f'map regions at 0x38: {kinds}')
    if 'valid' not in kinds: problems.append('no CRC-valid map at 0x38 (not a 0x38-format record)')
    if any(k == 'valid' for k in maps_at(sector, 0x40)): problems.append('CRC-valid map at 0x40 (already 0x40 format)')
    if sector[0x38+MAPS*MAP_SIZE:SECTOR] != b'\xff'*(SECTOR-0x38-MAPS*MAP_SIZE): problems.append('bytes after the six maps not erased')
    return problems

def migrate(sector):
    return sector[0:0x20] + b'\xff'*8 + sector[0x20:SECTOR-8]

class Fault(Exception): pass

class Executor:
    """Concrete P-code execution with byte-level taint from USERIF reads. Not a CPU model:
    MMIO reads return 0, interrupts and other tasks do not run, unfollowed calls are stubbed."""
    def __init__(self, app, build, userif, max_steps=3_000_000, gpio=None):
        self.app, self.b, self.max_steps = app, build, max_steps
        self.mem, self.taint, self.regs, self.rtaint = {}, {}, {}, {}
        self.userif = bytearray(userif)
        self.events, self.milestones, self.flash_ops, self.stubbed = [], [], [], {}
        self.heap = HEAP; self.files = {}; self.cache = {}; self.stack = []
        self.gpio = {0x16: 0} if gpio is None else gpio  # power key (PB6, active low) held at power-on; others released
        end = self.text_end = self.imm(0x1e00172)
        data_len, code_dst, code_len = self.imm(0x1e00178), self.imm(0x1e00192), self.imm(0x1e0019e)
        data_src = end - BASE
        for i in range(data_len): self.mem[0x840+i] = app[data_src+i]
        code_src = self.imm(0x1e00198) - BASE
        for i in range(code_len): self.mem[code_dst+i] = app[code_src+i]
        self.ram_code = (code_dst, code_dst+code_len)
    def imm(self, addr):
        b = self.app[addr-BASE:addr-BASE+6]
        return struct.unpack_from('<I', b, 2)[0]
    # memory
    def rbyte(self, a):
        if a in self.mem: return self.mem[a]
        if BASE <= a < BASE+len(self.app): return self.app[a-BASE]
        return 0
    def load(self, a, n):
        v = sum(self.rbyte(a+i) << 8*i for i in range(n))
        t = frozenset().union(*[self.taint.get(a+i, frozenset()) for i in range(n)])
        return v, t
    def store(self, a, n, v, t):
        if BASE <= a < BASE+len(self.app): raise Fault(f'store to flash {a:#x}')
        for i in range(n):
            self.mem[a+i] = (v >> 8*i) & 255
            if t: self.taint[a+i] = t
            else: self.taint.pop(a+i, None)
    # varnodes
    def get(self, vn):
        sp = vn.space.name
        if sp == 'const': return vn.offset, frozenset()
        if sp in ('register', 'unique'):
            v = sum(self.regs.get((sp, vn.offset+i), 0) << 8*i for i in range(vn.size))
            t = frozenset().union(*[self.rtaint.get((sp, vn.offset+i), frozenset()) for i in range(vn.size)])
            return v, t
        if sp == 'ram': return self.load(vn.offset, vn.size)
        raise Fault(f'space {sp}')
    def put(self, vn, v, t):
        v &= (1 << 8*vn.size) - 1
        sp = vn.space.name
        if sp == 'ram': return self.store(vn.offset, vn.size, v, t)
        for i in range(vn.size):
            self.regs[(sp, vn.offset+i)] = (v >> 8*i) & 255
            if t: self.rtaint[(sp, vn.offset+i)] = t
            else: self.rtaint.pop((sp, vn.offset+i), None)
    def reg(self, name, value=None, t=frozenset()):
        r = REGS[name]
        class V: pass
        vn = V(); vn.space = type('S', (), {'name': 'register'}); vn.offset = r.offset; vn.size = r.size
        if value is None: return self.get(vn)
        self.put(vn, value, t)
    # code
    def fetch(self, pc):
        if pc in self.cache: return self.cache[pc]
        if BASE <= pc < self.text_end: code = self.app[pc-BASE:pc-BASE+16]
        elif self.ram_code[0] <= pc < self.ram_code[1]: code = bytes(self.rbyte(pc+i) for i in range(16))
        else: raise Fault(f'pc outside executable ranges: {pc:#x}')
        try:
            ins = ctx.disassemble(code, pc, max_instructions=1).instructions[0]
        except Exception: raise Fault(f'undecodable instruction at {pc:#x}')
        ops = ctx.translate(code, pc, max_instructions=1).ops
        self.cache[pc] = (ins, ops); return ins, ops
    def event(self, kind, pc, **info):
        self.events.append(dict(kind=kind, pc=hex(pc), **info))
    @staticmethod
    def labels(t): return sorted(t)
    def sx(self, v, n): s = 1 << (8*n-1); return (v ^ s) - s
    def run(self, entry, args, stop):
        self.reg('sp', 0xf000); self.reg('rets', SENTINEL)
        for name, value in args.items(): self.reg(name, value)
        pc, steps = entry, 0
        while True:
            if pc == SENTINEL: return 'returned'
            if pc in stop: return stop[pc]
            if 0x100000 <= pc < 0x110000:
                args = [self.reg(f'r{k}') for k in range(4)]
                if pc in ROM: self.rom(ROM[pc], args, pc, 0)
                else: self.ret(0)
                pc = self.reg('rets')[0]; continue
            steps += 1
            if steps > self.max_steps: raise Fault(f'step budget exceeded at {pc:#x} (calls {[hex(x) for x in self.stack[-4:]]})')
            ins, ops = self.fetch(pc)
            if ins.mnem == 'mov' and f'#{self.b["pwm_table"]:#x}' in ins.body and 'LED PWM table' not in self.milestones: self.milestones.append('LED PWM table')
            nxt = pc + ins.length; i = 0
            while i < len(ops):
                op = ops[i]; name = op.opcode.name
                if name == 'IMARK': i += 1; continue
                if name in ('BRANCH', 'CBRANCH'):
                    take = True
                    if name == 'CBRANCH':
                        c, t = self.get(op.inputs[1]); take = bool(c)
                        if t: self.event('branch', pc, on=self.labels(t), taken=take)
                    if take:
                        tgt = op.inputs[0]
                        if tgt.space.name == 'const': i += self.sx(tgt.offset, tgt.size); continue
                        nxt = tgt.offset; break
                    i += 1; continue
                if name in ('BRANCHIND', 'RETURN', 'CALLIND'):
                    v, t = self.get(op.inputs[0])
                    if t:
                        self.event('switch', pc, on=self.labels(t), target=hex(v))
                        if not (BASE <= v < self.text_end or self.ram_code[0] <= v < self.ram_code[1]): raise Fault(f'settings-derived jump outside code at {pc:#x}: {v:#x}')
                    if name == 'CALLIND': nxt = self.call(v, pc, nxt)
                    else: nxt = v
                    break
                if name == 'CALL':
                    nxt = self.call(op.inputs[0].offset, pc, nxt); break
                if name == 'CALLOTHER': i += 1; continue
                vals = [self.get(x) for x in op.inputs]
                v = [x[0] for x in vals]; t = frozenset().union(*[x[1] for x in vals])
                if name == 'LOAD':
                    addr, at = vals[1]; n = op.output.size
                    if at: self.event('index', pc, on=self.labels(at), address=hex(addr))
                    if n in (2, 4) and addr % n: raise Fault(f'misaligned {n}-byte load at {pc:#x} ({addr:#x})')
                    r, rt = self.load(addr, n); self.put(op.output, r, rt | at); i += 1; continue
                if name == 'STORE':
                    addr, at = vals[1]; val, vt = vals[2]; n = op.inputs[2].size
                    if at: self.event('index', pc, on=self.labels(at), address=hex(addr), store=True)
                    if n in (2, 4) and addr % n: raise Fault(f'misaligned {n}-byte store at {pc:#x} ({addr:#x})')
                    self.store(addr, n, val, vt | at); i += 1; continue
                n = op.inputs[0].size
                if name in ('INT_DIV', 'INT_SDIV', 'INT_REM', 'INT_SREM'):
                    if vals[1][1]: self.event('divisor', pc, on=self.labels(vals[1][1]), value=v[1])
                    if v[1] == 0: raise Fault(f'divide by zero at {pc:#x}')
                if name in ('INT_LEFT', 'INT_RIGHT', 'INT_SRIGHT') and vals[1][1]:
                    self.event('shift', pc, on=self.labels(vals[1][1]), value=v[1])
                r = self.alu(name, v, n, op)
                self.put(op.output, r, t); i += 1
            pc = nxt
    def alu(self, name, v, n, op):
        m = (1 << 8*n) - 1
        if name == 'COPY': return v[0]
        if name == 'INT_ADD': return v[0] + v[1]
        if name == 'INT_SUB': return v[0] - v[1]
        if name == 'INT_MULT': return v[0] * v[1]
        if name == 'INT_DIV': return v[0] // v[1]
        if name == 'INT_REM': return v[0] % v[1]
        if name == 'INT_SDIV': a, b = self.sx(v[0], n), self.sx(v[1], n); return int(a / b)
        if name == 'INT_SREM': a, b = self.sx(v[0], n), self.sx(v[1], n); return a - int(a / b) * b
        if name == 'INT_AND': return v[0] & v[1]
        if name == 'INT_OR': return v[0] | v[1]
        if name == 'INT_XOR': return v[0] ^ v[1]
        if name == 'INT_NEGATE': return ~v[0]
        if name == 'INT_LEFT': return v[0] << v[1] if v[1] < 64 else 0
        if name == 'INT_RIGHT': return v[0] >> v[1]
        if name == 'INT_SRIGHT': return self.sx(v[0], n) >> min(v[1], 63)
        if name == 'INT_ZEXT': return v[0]
        if name == 'INT_SEXT': return self.sx(v[0], n)
        if name == 'INT_EQUAL': return int(v[0] == v[1])
        if name == 'INT_NOTEQUAL': return int(v[0] != v[1])
        if name == 'INT_LESS': return int(v[0] < v[1])
        if name == 'INT_LESSEQUAL': return int(v[0] <= v[1])
        if name == 'INT_SLESS': return int(self.sx(v[0], n) < self.sx(v[1], op.inputs[1].size))
        if name == 'INT_SLESSEQUAL': return int(self.sx(v[0], n) <= self.sx(v[1], op.inputs[1].size))
        if name == 'BOOL_NEGATE': return int(not v[0])
        if name == 'SUBPIECE': return v[0] >> 8*v[1]
        if name == 'LZCOUNT': return 8*n - (v[0] & m).bit_length()
        raise Fault(f'unsupported P-code {name}')
    # calls
    def ret(self, value=0, t=frozenset()):
        self.reg('r0', value, t)
    def call(self, target, pc, nxt):
        self.reg('rets', nxt)
        b = self.b; args = [self.reg(f'r{k}') for k in range(4)]
        if 0x100000 <= target < 0x110000:
            if target in ROM: return self.rom(ROM[target], args, pc, nxt)
            self.ret(0); return nxt
        sd = {v: k for k, v in b['sdfile'].items()}
        if target in sd: self.sdfile(sd[target], args, pc); return nxt
        if target == b['malloc']: self.ret(self.heap); self.heap += (args[0][0] + 15) & ~15; return nxt
        if target in b['gpio_read']: self.ret(self.gpio.get(args[0][0], 1)); return nxt
        if target == b['task_create']: return nxt
        if target in b['printf'] or target in (b['free'], b['delay'], b['battery_sample']) or not (0x1e03000 <= target < 0x1e10000) and not (0x4000 <= target < 0x8000):
            self.stubbed[hex(target)] = self.stubbed.get(hex(target), 0) + 1
            tainted = [k for k, (v, t) in enumerate(args) if t]
            if tainted and target not in b['printf'] and target != b['battery_sample']: self.event('stub-arg', pc, target=hex(target), args=tainted)
            self.ret(0); return nxt
        self.stack.append(target)
        return target
    def rom(self, name, args, pc, nxt):
        (a0, t0), (a1, t1), (a2, t2) = args[0], args[1], args[2]
        if t2: self.event('length', pc, fn=name, on=self.labels(t2), value=a2)
        if t0 or t1: self.event('index', pc, fn=name, on=self.labels(t0 | t1))
        if name == 'memcpy':
            for i in range(a2): v, t = self.load(a1+i, 1); self.store(a0+i, 1, v, t)
            self.ret(a0)
        elif name == 'memset':
            for i in range(a2): self.store(a0+i, 1, a1 & 255, t1)
            self.ret(a0)
        elif name == 'memcmp':
            r = 0
            for i in range(a2):
                x, y = self.rbyte(a0+i), self.rbyte(a1+i)
                if x != y: r = x - y; break
            self.ret(r & 0xffffffff)
        elif name == 'strlen':
            n = 0
            while self.rbyte(a0+n): n += 1
            self.ret(n)
        return nxt
    def cstr(self, a):
        s = bytearray()
        while self.rbyte(a+len(s)) and len(s) < 64: s.append(self.rbyte(a+len(s)))
        return s.decode('latin1')
    def sdfile(self, fn, args, pc):
        (a0, _), (a1, _), (a2, t2), (a3, _) = args
        if fn == 'fopen':
            path = self.cstr(a0)
            if not path.endswith('/USERIF'): raise Fault(f'unexpected file {path} at {pc:#x}')
            self.files[1] = 0; self.ret(1)
        elif fn == 'fseek': self.files[a0] = a1; self.ret(0)
        elif fn == 'fread':
            pos = self.files[a0]
            for i in range(a2):
                self.store(a1+i, 1, self.userif[pos+i], frozenset({pos+i}))
            self.files[a0] = pos + a2; self.flash_ops.append(('read', hex(pos), a2)); self.ret(a2)
        elif fn == 'fwrite':
            pos = self.files[a0]
            for i in range(a2): self.userif[pos+i] &= self.rbyte(a1+i)
            self.files[a0] = pos + a2; self.flash_ops.append(('write', hex(pos), a2)); self.ret(a2)
        elif fn == 'fattr': self.ret(0)
        elif fn == 'fsaddr': self.ret(USERIF)
        elif fn == 'erase':
            if not USERIF <= a1 < USERIF+2*SECTOR: raise Fault(f'erase outside USERIF {a1:#x}')
            off = (a1 - USERIF) & ~(SECTOR-1)
            self.userif[off:off+SECTOR] = b'\xff'*SECTOR; self.flash_ops.append(('erase', hex(USERIF+off), SECTOR)); self.ret(1)
        elif fn == 'fclose': self.ret(0)

def boot(app, name, userif, gpio=None):
    """Run the application's input/LED initialiser (APP_STA_CREATE) from entry to the emf task creation."""
    b = BUILDS[name]
    ex = Executor(app, b, userif, gpio=gpio)
    ex.store(0xe004, 4, 0xf, frozenset())
    try:
        outcome = ex.run(b['init'], {'r0': 0, 'r1': 1, 'r2': 0xe000}, {b['task_create']: 'reached emf task creation'})
    except Fault as fault:
        outcome = f'FAULT: {fault}'
    m = ex.mem; ms = b['m_storage']
    record = bytes(ex.rbyte(ms+i) for i in range(b['size']))
    kinds = {}
    for e in ex.events:
        key = (e['kind'], e['pc'])
        kinds.setdefault(key, e)
    return {'outcome': outcome, 'milestones': ex.milestones,
            'events': [dict(e, on=[hex(x) for x in e['on']] if 'on' in e else None) for e in kinds.values() if e['kind'] != 'branch'],
            'tainted_branches': len({e['pc'] for e in ex.events if e['kind'] == 'branch'}),
            'm_storage_after_init': record.hex(),
            'list_map_index_used': ex.rbyte(ms+2),
            'userif_ops': ex.flash_ops,
            'userif_after': bytes(ex.userif[:0x500]), 'stubbed_calls': len(ex.stubbed)}

def check_maps(app, name, sector, start):
    """Run the build's own api_storage_check_map on each 0xc8-byte region."""
    b = BUILDS[name]; out = []
    for i in range(MAPS):
        ex = Executor(app, b, sector)
        region = sector[start+i*MAP_SIZE:start+(i+1)*MAP_SIZE]
        for k, v in enumerate(region): ex.store(0xe000+k, 1, v, frozenset())
        args = {'r0': 0xe000} if name != 'sep2025' else {'r0': 0xe000, 'r1': MAP_SIZE}
        try:
            ex.run(b['check_map'], args, {}); out.append(ex.reg('r0')[0])
        except Fault as fault:
            out.append(f'FAULT {fault}')
    return out

def defaults(app, lo, hi):
    """(offset, default) pairs from the initialiser's 'if field == 0xff(ff) then default' pattern."""
    pairs = {}; pc = lo; prev = []
    while pc < hi:
        try:
            ins = ctx.disassemble(app[pc-BASE:pc-BASE+16], pc, max_instructions=1).instructions[0]
        except Exception:
            pc += 2; continue
        prev = (prev + [(ins.mnem, ins.body)])[-6:]
        if ins.mnem in ('sb', 'sh') and len(prev) >= 3:
            m1 = re.fullmatch(r'(r\d+), \[(r\d+) \+ (0x[0-9a-f]+)\]', ins.body)
            mv = re.fullmatch(r'(r\d+), #(0x[0-9a-f]+)', prev[-2][1]) if prev[-2][0] == 'mov' else None
            ld = [p for p in prev[:-2] if p[0] in ('lb.u', 'lh.u') and m1 and p[1].endswith(f'[{m1.group(2)} + {m1.group(3)}]')]
            if m1 and mv and ld: pairs[int(m1.group(3), 16)] = int(mv.group(2), 16)
        pc += ins.length
    return pairs

def sweep(app, lo, hi):
    out, pc = [], lo
    while pc < hi:
        try:
            ins = ctx.disassemble(app[pc-BASE:pc-BASE+16], pc, max_instructions=1).instructions[0]
            out.append((pc, ins.mnem, ins.body)); pc += ins.length
        except Exception:
            pc += 2
    return out

def syscfg_items(listing, read, write):
    """(id, length) immediates at syscfg_read/syscfg_write call sites."""
    found = {}
    for k, (a, m, b) in enumerate(listing):
        if m != 'call' or not b.startswith('0x') or int(b.split()[0], 16) not in (read, write): continue
        regs = {}
        for j in range(k-1, max(k-6, 0), -1):
            mm, bb = listing[j][1], listing[j][2]
            if mm in ('call', 'rts', 'goto') or mm.startswith('j'): break
            x = re.fullmatch(r'(r[0-2]), #(0x[0-9a-f]+)', bb)
            if mm == 'mov' and x and x.group(1) not in regs: regs[x.group(1)] = int(x.group(2), 16)
        if 'r0' in regs and 'r2' in regs:
            found.setdefault('read' if int(b.split()[0], 16) == read else 'write', set()).add((regs['r0'], regs['r2']))
    return {k: sorted(v) for k, v in found.items()}

def main():
    report = {}
    tester = TESTER.read_bytes(); unit1 = UNIT1.read_bytes()
    check(digest(tester) == SHA['tester'] and digest(unit1) == SHA['unit1'], 'dump hashes')
    apps = {'sep2025': Layout(tester).application(), 'oct2025': oem_application(),
            'glassly': (ROOT.parent/'firmware/dist/glassly-gamebrick-app.bin').read_bytes()}
    for k, a in apps.items(): check(digest(a) == SHA[k], f'{k} hash')
    old = tester[USERIF:USERIF+SECTOR]; new = migrate(old); erased = b'\xff'*SECTOR
    second = tester[USERIF+SECTOR:USERIF+2*SECTOR]; u1 = unit1[USERIF:USERIF+SECTOR]

    pre = {'tester': migration_preconditions(old), 'unit1 (0x40)': migration_preconditions(u1),
           'erased': migration_preconditions(erased), 'migrated': migration_preconditions(new)}
    report['preconditions'] = pre
    check(pre['tester'] == [], 'tester record must satisfy the preconditions')
    check(all(pre[k] for k in ('unit1 (0x40)', 'erased', 'migrated')), 'non-0x38 sectors must be refused')
    report['sector_0x7e000_erased_on_tester'] = check(second == erased, 'tester 0x7e000 erased')
    report['maps'] = {'tester @0x38': maps_at(old, 0x38), 'migrated @0x40': maps_at(new, 0x40), 'unit1 @0x40': maps_at(u1, 0x40)}
    check(report['maps']['migrated @0x40'] == ['valid']*MAPS, 'all six maps valid after the shift')
    report['migrated_vs_unit1_record'] = [(hex(i), hex(new[i]), hex(u1[i])) for i in range(0x40) if new[i] != u1[i]]
    check(report['migrated_vs_unit1_record'] == [('0x1', '0x0', '0x72')], 'migrated record should equal a factory 0x40 record except reset_reson')
    report['check_map'] = {
        'oct2025 on migrated maps': check_maps(apps['oct2025'], 'oct2025', new, 0x40),
        'oct2025 on erased regions': check_maps(apps['oct2025'], 'oct2025', erased, 0x40),
        'sep2025 on original maps': check_maps(apps['sep2025'], 'sep2025', old, 0x38),
        'sep2025 on migrated sector at its own offsets': check_maps(apps['sep2025'], 'sep2025', new, 0x38)}
    check(report['check_map']['oct2025 on migrated maps'] == [1]*MAPS, 'Oct accepts every migrated map')
    check(report['check_map']['sep2025 on original maps'] == [1]*MAPS, 'Sep accepts its own maps')
    check(report['check_map']['oct2025 on erased regions'] == [0]*MAPS, 'Oct rejects erased regions')

    d_oct = defaults(apps['oct2025'], 0x1e0b0e0, 0x1e0b3e0); d_sep = defaults(apps['sep2025'], 0x1e0b100, 0x1e0b3f0)
    oct_f = {k-0x80: v for k, v in d_oct.items() if k >= 0x80}; sep_f = {k-0x1c4: v for k, v in d_sep.items() if k >= 0x1c4}
    report['erased_defaults'] = {'oct2025': {hex(k): hex(v) for k, v in sorted(oct_f.items())}, 'sep2025': {hex(k): hex(v) for k, v in sorted(sep_f.items())}}
    shifted = {k - (8 if k >= 0x28 else 0): v for k, v in oct_f.items()}
    report['defaults_correspond_with_shift_at_0x20'] = check(shifted == sep_f, 'erased defaults must correspond after the shift')

    listings = {k: sweep(apps[k], BASE, BASE + 0x2de88) for k in ('sep2025', 'oct2025')}
    report['syscfg_items'] = {'sep2025': syscfg_items(listings['sep2025'], 0x1e1c684, 0x1e1c75c), 'oct2025': syscfg_items(listings['oct2025'], 0x1e1c67a, 0x1e1c752)}
    check(report['syscfg_items']['sep2025'] == report['syscfg_items']['oct2025'], 'VM item ids/lengths differ')

    boots, summary = {}, {}
    cases = [('oct2025', 'tester original', old), ('oct2025', 'migrated', new), ('glassly', 'migrated', new), ('oct2025', 'erased', erased),
             ('glassly', 'erased', erased), ('oct2025', 'unit1 (0x40 factory)', u1),
             ('sep2025', 'tester original', old), ('sep2025', 'erased', erased), ('sep2025', 'migrated', new)]
    for app_name, label, sector in cases:
        for pa1 in (1, 0):
            for pa2 in (1, 0):
                r = boot(apps[app_name], app_name, sector + second, gpio={0x16: 0, 1: pa1, 2: pa2})
                after = r.pop('userif_after') + b'\xff'*(SECTOR-0x500)
                written = [op for op in r['userif_ops'] if op[0] != 'read']
                key = f'{app_name} / {label} / PA1={pa1} PA2={pa2}'
                events = sorted({(e['kind'], e['pc'], str(e.get('value', e.get('target', '')))) for e in r['events'] if e['kind'] not in ('stub-arg',)})
                boots[key] = {'outcome': r['outcome'], 'milestones': r['milestones'], 'list_map_index': r['list_map_index_used'],
                              'userif_written': written, 'events': events,
                              'record_after': after[:0x48].hex() if written else None,
                              'preconditions_after': migration_preconditions(after) if written else None,
                              'format_after': ('0x40' if 'valid' in maps_at(after, 0x40) else '0x38' if 'valid' in maps_at(after, 0x38) else 'none') if written else 'unchanged'}
                summary[key] = r['outcome']
    report['boot'] = boots
    for key, outcome in summary.items():
        if '/ tester original /' in key and key.startswith('oct2025'):
            check(outcome == 'FAULT: divide by zero at 0x1e0b322', f'{key}: baseline must reproduce the div0')
        else:
            check(outcome == 'reached emf task creation' and 'LED PWM table' in boots[key]['milestones'], f'{key} must reach LED setup and task creation')
    for pos in ('PA1=1 PA2=1', 'PA1=1 PA2=0', 'PA1=0 PA2=1', 'PA1=0 PA2=0'):
        mig, ref = boots[f'oct2025 / migrated / {pos}'], boots[f'oct2025 / unit1 (0x40 factory) / {pos}']
        same = [e for e in mig['events'] if e[0] != 'index' or 'strlen' not in e[2]] == [e for e in ref['events'] if e[0] != 'index' or 'strlen' not in e[2]]
        report.setdefault('oct_migrated_events_equal_unit1', {})[pos] = same
    divisor_target = new[0x3b]
    report['divisor_byte'] = {'migrated value': divisor_target, 'any partial program from 0xff can reach 0': divisor_target == 0}
    check(divisor_target != 0, 'migrated divisor byte must be nonzero')
    report['failures'] = failures
    print(json.dumps(report, indent=1, default=str))
    return 1 if failures else 0

if __name__ == '__main__':
    sys.exit(main())
