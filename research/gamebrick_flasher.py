"""One-shot Gamebrick flasher: take any known Gamebrick Mini straight to the Glassly firmware.

Everything is derived from the connected unit's own flash. The flash is read twice and kept
as a backup; its partition tables must be one of the known layouts and its application one of
the known builds (flash_layout.py). The Glassly and official applications ship in firmware/dist
and are hash-pinned; the official update archive is only needed to rebuild them. Only the
application area is written: the storage partitions the tables declare, the key/MAC sector
and everything else stay as read.
"""
import hashlib, io, json, subprocess, sys, tempfile, urllib.request, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'jl-misctools/firmware'))
from stock_update import build, digest, require, OEM_SHA
from custom_image import patch_app
from flash_layout import APPLICATIONS, HARDWARE_VERIFIED, LAYOUTS, Layout, classify

SIZE = 0x80000

OEM_ZIP_URL = 'https://media.iine.top/legacy-assets/6dd5d46599c6e1eeb8bd2623c15d14c7a3aee61163f46da0df38953c690dac61-zip'
OEM_ZIP_SHA = '6dd5d46599c6e1eeb8bd2623c15d14c7a3aee61163f46da0df38953c690dac61'
OEM_UFW_SHA = '73005e7c885aab2a644adfdf2dbadc01802b34427e9e6febf823f50d4d7745e9'
CUSTOM_APP_SHA = '495ce9131d2cadebd558ec6d5ebfd51b6afa1ba957cba5c7f5dd331fcba9f432'
DIST = ROOT.parent/'firmware/dist'
PAYLOAD = DIST/'vendor-payload.bin'
GLASSLY_APP = DIST/'glassly-gamebrick-app.bin'
OFFICIAL_APP = DIST/'iine-official-app.bin'
MANIFEST = ROOT.parent/'docs/evidence/q32s-payload.json'


def oem_archive(path=None, log=print):
    """The official update ZIP: a local copy, a cached download, or a fresh one. Hash-pinned."""
    cache = ROOT/'stock-update.zip'
    for candidate in ([Path(path)] if path else []) + [cache]:
        if candidate.exists():
            data = candidate.read_bytes()
            require(digest(data) == OEM_ZIP_SHA, f'{candidate} is not the pinned IINE update archive')
            return data
    log(f'Downloading the official IINE update ({OEM_ZIP_URL})')
    with urllib.request.urlopen(OEM_ZIP_URL, timeout=120) as response:
        data = response.read()
    require(digest(data) == OEM_ZIP_SHA, 'Downloaded archive hash differs from the pinned IINE update')
    cache.write_bytes(data)
    return data


def oem_application(archive=None):
    """The unmodified official application: the committed copy, or extracted from the update
    archive with the independent upstream unpacker. Hash-pinned either way."""
    if archive is None:
        app = OFFICIAL_APP.read_bytes()
        require(digest(app) == OEM_SHA, 'Committed official application hash mismatch')
        return app
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        members = [m for m in z.namelist() if m.lower().endswith('.ufw')]
        require(len(members) == 1, 'Expected one .ufw in the update archive')
        ufw = z.read(members[0])
    require(digest(ufw) == OEM_UFW_SHA, 'Update firmware hash differs from the pinned IINE reader update')
    tool = ROOT/'jl-misctools/firmware'
    with tempfile.TemporaryDirectory() as temp:
        (Path(temp)/'stock.ufw').write_bytes(ufw)
        result = subprocess.run([sys.executable, '-E', '-s', str(tool/'fwunpack_newfw.py'), '--dirname', temp + '/out', temp + '/stock.ufw'],
                                capture_output=True, text=True, cwd=tool)
        require(result.returncode == 0, 'Unpacking the official update failed: ' + result.stderr[-400:])
        app = (Path(temp)/'out/files/app.bin').read_bytes()
    require(digest(app) == OEM_SHA, 'Official application hash mismatch')
    return app


def custom_application(oem=None):
    """The reviewed Glassly application: the committed copy, or the OEM bytes plus the pinned
    hooks and payload. Hash-pinned either way."""
    if oem is None:
        app = GLASSLY_APP.read_bytes()
        require(digest(app) == CUSTOM_APP_SHA, 'Committed Glassly application hash mismatch')
        return app
    payload = PAYLOAD.read_bytes()
    manifest = json.loads(MANIFEST.read_text())
    require(digest(payload) == manifest['payload_sha256'], 'Payload differs from the reviewed build')
    patched, _ = patch_app(oem, payload, manifest, decode=False)
    require(digest(patched) == CUSTOM_APP_SHA, 'Patched application differs from the reviewed hash')
    return patched


KNOWN_STATES = ('factory', 'factory-2025-09', 'stock', 'custom')


def plan(current, oem, mode, custom=None, backup=None, flash_id=None, allow_unverified=False):
    """Source and target images for `mode` from the live flash, both carrying its storage.
    `custom` defaults to the committed Glassly application. `restore-backup` puts back the
    application found in `backup`, an earlier full read of this same kind of controller."""
    state = classify(current)
    require(state in KNOWN_STATES, f'Unrecognised flash contents ({state}); refusing to write. Keep the saved backup and ask for help.')
    layout = Layout(current)
    if mode in ('install', 'restore') and not allow_unverified:
        require((layout.fingerprint, flash_id) in HARDWARE_VERIFIED,
                'This is a kind of Gamebrick the Glassly firmware has not been flashed and seen booting on '
                f'(flash layout: {layout.describe()}; flash part {flash_id:#08x}). It can be backed up and have its own '
                'backup restored, nothing more. Send the backup folder so this kind can be reviewed; the first flash on a '
                'new kind of unit is done on a developer-owned controller. Nothing was written.'
                if flash_id is not None else 'Flash part unknown; nothing was written.')
    sha = digest(current)
    stock = build(current, oem, sha)
    if mode == 'install':
        target, expected = build(current, custom or custom_application(), sha), 'custom'
    elif mode == 'restore':
        target, expected = stock, 'stock'
    elif mode == 'restore-backup':
        require(backup is not None and len(backup) == SIZE, 'A full 512 KiB backup read is required')
        expected = classify(backup)
        require(expected in KNOWN_STATES and Layout(backup).fingerprint == layout.fingerprint,
                f'The backup is not a known image from this kind of controller ({expected})')
        target = build(current, Layout(backup).application(), sha)
    else:
        raise RuntimeError('Invalid operation')
    require(classify(target) == expected, 'Derived image does not carry the reviewed application')
    require(target[:layout.base] == current[:layout.base] and target[layout.limit:] == current[layout.limit:],
            'Plan would alter bytes outside the application area')
    sectors = [a for a in range(0, SIZE, 4096) if current[a:a+4096] != target[a:a+4096]]
    return {'state': state, 'layout': layout.describe(), 'chip_key': f'{layout.key:#06x}', 'target': target, 'stock': stock,
            'target_state': expected, 'changed_sectors': sectors, 'current_sha256': sha, 'target_sha256': digest(target),
            'stock_sha256': digest(stock)}
