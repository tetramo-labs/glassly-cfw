"""Offline evidence for the 2026-11-13 no-boot report on the IINE-layout unit.

See docs/no-boot-investigation.md. Reads the saved dumps and pinned applications only; no USB IO.
Prints a JSON report and exits 1 if any expectation fails.
"""
import hashlib, json, re, struct, sys
from pathlib import Path
import pypcode
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'jl-misctools/firmware'))
from flash_layout import Layout
from gamebrick_flasher import oem_application
from stock_update import build

BASE = 0x1e00120
USERIF = 0x7d000
MAP_MAX = 0xc8
DUMPS = {
    'tester': (ROOT/'device-backup-20261113-tester/flash-pass1.bin', '4d6d248101d342755bf51c2b18d7f81dd1b6c0629a5f6516f9edab8d1845df89'),
    'unit1': (ROOT/'device-backup-20261022-233350/flash-pass1.bin', '9b7c57387ded72fadd162599cfb2b3797fb27e10759918d4e06f879740577cb3'),
    'unit2': (ROOT/'device-backup-20261028-192851/flash-pass1.bin', '221856d20bf10ff8f9a0c4cbe38ed5efeb98f7de41625a48c916d19c0d7466f5'),
}
APPS = {
    'sep2025': 'e858401635ddbc953ef5f6bc5a6d17dff9635a7536bb0d7a91c8d7824ffb21af',
    'oct2025': '2fb44f4235bd4ed7183439f31ee2a31fb0052d19dd736e20d1d251fd5e1ff259',
    'may2026': '902aedc30a84c9ae777e3cbdd12ff5737ac17b7ee3f5288f76c7aa86fe267c97',
    'glassly': '495ce9131d2cadebd558ec6d5ebfd51b6afa1ba957cba5c7f5dd331fcba9f432',
}
WRITTEN_SHA = 'af4af1e63273fe2240deddd0cb57589e1cea27ddda45952e2da8bb17fbbdc8a7'
# Oct 2025 hook sites and stock symbols (custom_image.py, firmware/payload.ld) and their Sep 2025 counterparts,
# found by byte alignment of the two builds; each pair is checked here by disassembly.
SEP_PORT = [
    ('gb_stock_att', 0x1e034b4, 0x1e03570, 'push {rets, r5, r4}'),
    ('gb_stock_ccc', 0x1e041b6, 0x1e04272, 'goto'),
    ('gb_stock_ble_event', 0x1e0520c, 0x1e052be, 'push rets'),
    ('gb_stock_handler', 0x1e0ce10, 0x1e0cdae, 'push {rets, r15, r14, r13, r12, r11, r10, r9, r8, r7, r6, r5, r4}'),
    ('gb_stock_task_entry', 0x1e0ee68, 0x1e0eea4, 'add sp, #-0x58'),
    ('gb_stock_set_ccc', 0x1e14114, 0x1e1411c, 'push {rets, r7, r6, r5, r4}'),
    ('task create', 0x1e0bcac, 0x1e0bc58, 'mov r0, #'),
    ('task stack 0x800', 0x1e0bcb6, 0x1e0bc62, 'mov r3, #0x800'),
    ('task tick call', 0x1e0f194, 0x1e0f1a4, 'call'),
    ('CCC setter call', 0x1e04b86, 0x1e04c38, 'call'),
    ('BLE register moves', 0x1e05270, 0x1e05322, 'mov r1, r5'),
    ('BLE unchanged-state branch', 0x1e05256, 0x1e05308, 'jeq r2, r5'),
    ('BLE event call', 0x1e05274, 0x1e05326, 'call'),
    ('debug_init text limit', 0x1e10a90, 0x1e10a98, 'mov r0, #'),
    ('startup BSS count', 0x1e00138, 0x1e00138, 'mov r2, #'),
    ('startup data copy source', 0x1e00172, 0x1e00172, 'mov r1, #'),
]

arch = pypcode.Arch('Jieli', str(ROOT/'q32s-analysis/processor/data/languages/JieLi.ldefs'))
ctx = pypcode.Context(next(x for x in arch.languages if x.id == 'q32s:LE:32:default'))
failures = []

def check(ok, message):
    if not ok: failures.append(message)
    return ok
def digest(data): return hashlib.sha256(data).hexdigest()
def ins(app, addr):
    i = ctx.disassemble(app[addr-BASE:addr-BASE+16], addr, max_instructions=1).instructions[0]
    return i.length, i.mnem, i.body
def text(app, addr):
    _, m, b = ins(app, addr); return f'{m} {b}'
def sweep(app, end):
    out, addr = [], BASE
    while addr < end:
        try:
            n, m, b = ins(app, addr); out.append((addr, m, b)); addr += n
        except Exception:
            addr += 2
    return out
def text_end(app):
    m = re.match(r'r1, #(0x[0-9a-f]+)', ins(app, 0x1e00172)[2])
    return int(m.group(1), 16)

def storage_layout(listing):
    """api_storage_init: api_flash_read(0, &m_storage, sizeof m_storage), then the divisor read 500/x."""
    read = div = None
    for k, (a, m, b) in enumerate(listing):
        if m == 'mov' and re.fullmatch(r'r2, #0x(38|40)', b) and listing[k-1][2] == 'r0, #0x0' and listing[k+1][1] == 'call':
            base = re.fullmatch(r'r1, (r\d+), #(0x[0-9a-f]+)', listing[k-2][2])
            if base: read = (a, int(b.split('#')[1], 16), base.group(1), int(base.group(2), 16))
        if m == 'div.u' and b == 'r0, r2, r0' and listing[k-1][2] == 'r2, #0x1f4':
            load = next(x for x in reversed(listing[k-7:k]) if x[1] == 'lb.u' and x[2].startswith('r0, ['))
            reg, off = re.fullmatch(r'r0, \[(r\d+) \+ (0x[0-9a-f]+)\]', load[2]).groups()
            div = (a, load[0], reg, int(off, 16))
    return read, div

def run_divisor(app, start, stop, reg, reg_value, memory):
    """Execute the actual instructions from the divisor load to the division with m_storage in memory."""
    regs, mem, pc = {}, dict(memory), start
    def rd(vn):
        if vn.space.name == 'const': return vn.offset
        if vn.space.name == 'register': return regs.get((vn.offset, vn.size), 0)
        if vn.space.name == 'unique': return regs.get(('u', vn.offset, vn.size), 0)
        return None
    def wr(vn, value):
        key = (vn.offset, vn.size) if vn.space.name == 'register' else ('u', vn.offset, vn.size)
        regs[key] = value & ((1 << 8*vn.size) - 1)
    r = ctx.registers[reg]; regs[(r.offset, r.size)] = reg_value
    while pc <= stop:
        n = ins(app, pc)[0]; nxt = pc + n
        for op in ctx.translate(app[pc-BASE:pc-BASE+16], pc, max_instructions=1).ops:
            name, v = op.opcode.name, [rd(x) for x in op.inputs]
            if name == 'IMARK': continue
            if name == 'LOAD': wr(op.output, int.from_bytes(bytes(mem.get(v[1]+i, 0) for i in range(op.output.size)), 'little'))
            elif name == 'STORE':
                for i in range(op.inputs[2].size): mem[v[1]+i] = (v[2] >> 8*i) & 255
            elif name == 'COPY': wr(op.output, v[0])
            elif name == 'INT_ADD': wr(op.output, v[0] + v[1])
            elif name == 'INT_ZEXT': wr(op.output, v[0])
            elif name == 'INT_NOTEQUAL': wr(op.output, int(v[0] != v[1]))
            elif name == 'INT_EQUAL': wr(op.output, int(v[0] == v[1]))
            elif name == 'CBRANCH':
                if rd(op.inputs[1]): nxt = op.inputs[0].offset; break
            elif name == 'INT_DIV':
                if v[1] == 0: return {'dividend': v[0], 'divisor': 0, 'result': 'DIV0'}
                wr(op.output, v[0] // v[1]); return {'dividend': v[0], 'divisor': v[1], 'result': v[0] // v[1]}
            else: raise ValueError(f'unsupported P-code {name} at {pc:x}')
        pc = nxt
    raise ValueError('division not reached')

def userif_format(image):
    """sizeof(m_storage) recorded in USERIF: where CRC-valid LiteEMF list maps start (CRC-16/MODBUS)."""
    u = image[USERIF:USERIF+0x2000]
    def modbus(data, crc=0xffff):
        for b in data:
            crc ^= b
            for _ in range(8): crc = (crc >> 1) ^ 0xa001 if crc & 1 else crc >> 1
        return crc
    found = {}
    for size in (0x38, 0x40):
        valid = []
        for i in range(6):
            o = size + i*MAP_MAX
            crc, res, mx, ml = struct.unpack_from('<HHHH', u, o)
            if mx == MAP_MAX and ml <= MAP_MAX - 8 and modbus(u[o+2:o+8+ml]) == crc: valid.append(i)
        found[size] = valid
    sizes = [s for s, v in found.items() if v]
    return {'m_storage_size': sizes[0] if len(sizes) == 1 else None, 'valid_maps': {hex(s): v for s, v in found.items()}}

report = {}
images = {}
for name, (path, sha) in DUMPS.items():
    images[name] = path.read_bytes()
    check(digest(images[name]) == sha, f'{name} dump hash')
apps = {'sep2025': Layout(images['tester']).application(), 'may2026': Layout(images['unit1']).application(),
        'oct2025': oem_application(), 'glassly': (ROOT.parent/'firmware/dist/glassly-gamebrick-app.bin').read_bytes()}
for name, sha in APPS.items(): check(digest(apps[name]) == sha, f'{name} application hash')

# The 2026-11-13 install wrote only the application area; plan() has since gained the USERIF migration.
tester_sha = digest(images['tester'])
target, stock = build(images['tester'], apps['glassly'], tester_sha), build(images['tester'], apps['oct2025'], tester_sha)
check(digest(target) == WRITTEN_SHA, 'rebuilt written image differs from the verified flash')
check(Layout(target).application() == apps['glassly'], 'written image does not carry the Glassly application')
check(target[USERIF:USERIF+0x2000] == images['tester'][USERIF:USERIF+0x2000], 'USERIF was not preserved')
ufw = (ROOT/'unpacked/decrypted.bin').read_bytes()
stock_layout = Layout(stock); end = stock_layout.base + stock_layout.used
report['iine_update_image'] = {
    'stock_build_equals_ufw_over_used_area': check(bytes(stock_layout.plain[stock_layout.base:end]) == ufw[stock_layout.base:end], 'stock build differs from IINE ufw'),
    'used_area': [hex(stock_layout.base), hex(end)], 'glassly_area_end': hex(Layout(target).base + Layout(target).used)}

listings = {name: sweep(app, text_end(app)) for name, app in apps.items()}
report['builds'] = {}
for name, app in apps.items():
    read, div = storage_layout(listings[name])
    emu = any(m == 'mov' and b == 'r0, #0x80000017' for _, m, b in listings[name])
    report['builds'][name] = {'text_end': hex(text_end(app)), 'emu_con_0x80000017': emu,
        'storage_read': read and {'at': hex(read[0]), 'sizeof_m_storage': hex(read[1])},
        'divisor': div and {'div_at': hex(div[0]), 'm_storage_offset': hex(div[3] - read[3])}}
    check(emu and read and div and div[2] == read[2], f'{name}: storage read / divisor / EMU_CON pattern not found')
    report['builds'][name]['_read'], report['builds'][name]['_div'] = read, div
check(report['builds']['sep2025']['storage_read']['sizeof_m_storage'] == '0x38', 'Sep reads 0x38')
for name in ('oct2025', 'may2026', 'glassly'): check(report['builds'][name]['storage_read']['sizeof_m_storage'] == '0x40', f'{name} reads 0x40')

report['userif'] = {name: userif_format(image) for name, image in images.items()}
report['userif']['written_target'] = userif_format(target)
matrix = {}
for app_name, info in report['builds'].items():
    read, div = info.pop('_read'), info.pop('_div')
    for unit, image in list(images.items()):
        m_storage = 0x10000
        memory = {m_storage + i: b for i, b in enumerate(image[USERIF:USERIF+read[1]])}
        matrix[f'{app_name} on {unit} USERIF'] = run_divisor(apps[app_name], div[1], div[0], div[2], m_storage - read[3], memory)
report['divisor_matrix'] = matrix
check(matrix['glassly on tester USERIF']['result'] == 'DIV0' and matrix['oct2025 on tester USERIF']['result'] == 'DIV0', 'tester USERIF should give divisor 0')
check(all(v['result'] != 'DIV0' for k, v in matrix.items() if 'tester' not in k or k.startswith('sep2025')), 'unexpected DIV0')

g, o = apps['glassly'], apps['oct2025']
diff = [i for i in range(len(o)) if g[i] != o[i]]
report['glassly_vs_oct'] = {'differing_bytes_before_payload': [hex(BASE+i) for i in diff], 'appended': len(g) - len(o),
    'identical_through_emf_init_0x1e0afd8_0x1e0bca0': check(g[0x1e0afd8-BASE:0x1e0bca0-BASE] == o[0x1e0afd8-BASE:0x1e0bca0-BASE], 'Glassly differs in emf init')}

def gpio_config_calls(listing, target):
    calls = []
    for k, (a, m, b) in enumerate(listing):
        if m == 'call' and b.startswith(hex(target)):
            r0, r1 = listing[k-2][2], listing[k-1][2]
            if r0.startswith('r0, #') and r1.startswith('r1, #'): calls.append((int(r0[5:], 16), int(r1[5:], 16)))
    return calls
sep, octb = apps['sep2025'], apps['oct2025']
gpio_sep, gpio_oct = gpio_config_calls(listings['sep2025'], 0x1e04174), gpio_config_calls(listings['oct2025'], 0x1e040b8)
report['board_config'] = {
    'gpio_input_config_calls_oct': [f'gpio {p:#x} mode {mode}' for p, mode in gpio_oct],
    'gpio_input_config_identical': check(gpio_sep == gpio_oct and len(gpio_oct) == 15, 'GPIO input configuration differs'),
    'led_pwm_table_identical': check(sep[0x1e22574-BASE:0x1e22598-BASE] == octb[0x1e2258c-BASE:0x1e225b0-BASE], 'LED PWM table differs'),
    'gatt_profile_identical': check(sep[0x1e220a6-BASE:0x1e220a6-BASE+945] == octb[0x1e220be-BASE:0x1e220be-BASE+945], 'GATT profile differs'),
    'flash_id_immediates': sorted({b for n in listings for _, m, b in listings[n] if re.search(r'#0xcd7[01]13\b|#0x137[01]cd\b', b)}),
}
report['sep_port_map'] = []
for label, octa, sepa, expect in SEP_PORT:
    o_t, s_t = text(octb, octa), text(sep, sepa)
    ok = check(s_t.startswith(expect) and o_t.split()[0] == s_t.split()[0], f'Sep counterpart of {label}')
    report['sep_port_map'].append({'site': label, 'oct': hex(octa), 'sep': hex(sepa), 'oct_ins': o_t, 'sep_ins': s_t, 'ok': ok})
report['failures'] = failures
print(json.dumps(report, indent=1))
sys.exit(1 if failures else 0)
