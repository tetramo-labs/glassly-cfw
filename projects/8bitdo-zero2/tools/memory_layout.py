"""Pinned stock memory constraints; no address is approved for patch placement."""
import struct

from firmware_image import sha256
from startup import BASE, reconstruct

# r0=pool head, r1=block storage, r2=count, r3=stride at 0x01023bb4.
# Independently checked by executing the unmodified initializer in Unicorn.
POOLS = (
    (0x206e0, 0x22064, 3, 600),
    (0x206e4, 0x2276c, 4, 20),
    (0x206e8, 0x227bc, 4, 64),
    (0x206ec, 0x228bc, 3, 60),
    (0x206f0, 0x22970, 1, 16),
    (0x206f4, 0x22980, 3, 40),
    (0x206f8, 0x229f8, 5, 28),
    (0x206fc, 0x22a84, 3, 12),
)


def analyze(data):
    if sha256(data[0xbbb4:0xbcbe]) != '95341e26f390d13283591431b2aa2be8c46c450c062d0a3fa0f10d6ef41a522b':
        raise ValueError('Pool initialization differs from audited stock instructions')
    records, _, consumed = reconstruct(data)
    compressed_end = records[0]['source'] - BASE + consumed
    tail = records[1]['source'] - BASE
    if len(data) != 0x11e00 or tail != 0x11c04 or compressed_end != 0x11c02:
        raise ValueError('Unsupported stock tail layout')
    if any(data[compressed_end:]):
        raise ValueError('Stock alignment/tail bytes changed')
    if data[0x186c:0x1872] != bytes.fromhex('f0b5ffb0cab0'):
        raise ValueError('Unsupported event-dispatcher prologue')
    if data[0xcf48:0xcf4a] != bytes.fromhex('86b0'):
        raise ValueError('Unsupported main prologue')
    sp = struct.unpack_from('<I', data, 0x210)[0]
    if sp != 0x2ff00:
        raise ValueError('Unsupported startup stack')
    return {
        'section_sha256': sha256(data),
        'placement_approved': False,
        'ram': {
            'initialized_start': 0x20000, 'initialized_end': 0x2078c,
            'zero_start': 0x2078c, 'zero_end': 0x22b18,
            'pools': [dict(head=h, start=s, end=s+n*z, count=n, stride=z)
                      for h, s, n, z in POOLS],
            'pool_storage_bytes': sum(n*z for _, _, n, z in POOLS),
            'boot_fields': [dict(address=0x2fff0, size=4, role='mode/restart marker'),
                            dict(address=0x2fff4, size=4, role='startup version marker')],
            'unproven_interval': {'start': 0x22b18, 'end': sp,
                                 'size': sp - 0x22b18,
                                 'free_ram_claimed': False},
        },
        'stack': {
            'initial_sp': sp, 'main_local_bytes': 24,
            'event_dispatcher_frame_bytes': 20 + 508 + 296,
            'main_plus_dispatcher_bytes': 24 + 20 + 508 + 296,
            'worst_case_bound': None,
            'caveat': 'These frames exclude callees, ROM routines, exception frames and nesting',
        },
        'image_tail': {
            'compressed_data_end_offset': compressed_end,
            'alignment_bytes': tail - compressed_end,
            'offset': tail, 'address': BASE + tail, 'size': len(data) - tail,
            'sha256': sha256(data[tail:]),
            'reclaimable': False,
            'caveat': 'Package padding is not free flash: live readback differs in this region (see findings.md); preserve it, with no placement approved',
        },
        'external_arm_rom_calls': [
            dict(call_site=0x1024e84, thumb_target=0x442d, sdk_name='INIT_OTP'),
            dict(call_site=0x10250b4, thumb_target=0x45d9, argument=0x20000,
                 sdk_name='READ_CHIPID'),
            dict(call_site=0x1024154, thumb_target=0x4481, sdk_name='DEINIT_OTP'),
        ],
        'rom_symbol_source': 'docs/evidence/references.json:rt_thread_core_rom_api',
        'caveat': 'Selected observed constraints, not a complete memory or call graph; ROM implementation is absent',
    }
