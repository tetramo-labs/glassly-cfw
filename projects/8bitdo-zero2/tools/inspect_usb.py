"""Read macOS USB registry descriptors for Zero 2 / candidate 8BitDo bootloaders.

No device opens, control transfers, output reports, resets or firmware writes.
Unique identifiers and full target subtrees are saved only under ignored build/.
Bootloader VID/PID pairs are shared by other products: a match is a candidate,
not an assertion that the device is the user's controller.
"""
import json
import plistlib
import subprocess
import sys
from datetime import datetime, timezone

from firmware_image import ROOT, load_stock, sha256

IDS = {(0x2dc8, 0x9018): 'Zero 2 runtime',
       (0x2dc8, 0x3208): 'candidate 8BitDo Boot (observed after Zero 2 mode change)',
       (0x0483, 0x5760): 'candidate shared 8BitDo bootloader',
       (0x2dc8, 0x5750): 'candidate shared 8BitDo bootloader'}


def walk(node):
    if isinstance(node, dict):
        yield node
        for child in node.get('IORegistryEntryChildren', []):
            yield from walk(child)


def clean(value):
    if isinstance(value, bytes):
        return {'hex': value.hex()}
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def summarize(node, payloads):
    interfaces, descriptors = [], set()
    for child in walk(node):
        if child.get('IOObjectClass') == 'IOUSBHostInterface':
            interfaces.append({k: child.get(k) for k in (
                'bInterfaceNumber', 'bAlternateSetting', 'bInterfaceClass',
                'bInterfaceSubClass', 'bInterfaceProtocol', 'bNumEndpoints')})
        if isinstance(child.get('ReportDescriptor'), bytes):
            descriptors.add(child['ReportDescriptor'])
    report = []
    for descriptor in sorted(descriptors):
        report.append(dict(size=len(descriptor), sha256=sha256(descriptor),
                           stock_offsets=[data.find(descriptor) for data in payloads]))
    return dict(role=IDS[(node['idVendor'], node['idProduct'])],
                product=node.get('USB Product Name'),
                vid=f"0x{node['idVendor']:04x}", pid=f"0x{node['idProduct']:04x}",
                usb_bcdDevice=node.get('bcdDevice'),
                bcdDevice_is_firmware_version=False,
                configurations=node.get('bNumConfigurations'),
                interfaces=interfaces, hid_report_descriptors=report,
                exact_installed_firmware_identified=False)


def main():
    if sys.platform != 'darwin':
        raise SystemExit('This registry reader requires macOS')
    _, _, payloads = load_stock()
    command = ['/usr/sbin/ioreg', '-r', '-c', 'IOUSBHostDevice', '-l', '-w', '0', '-a']
    result = subprocess.run(command, capture_output=True, check=True, timeout=20)
    tree = plistlib.loads(result.stdout)
    roots = tree if isinstance(tree, list) else [tree]
    selected = [n for root in roots for n in walk(root)
                if n.get('IOObjectClass') == 'IOUSBHostDevice' and
                (n.get('idVendor'), n.get('idProduct')) in IDS]
    now = datetime.now(timezone.utc)
    summary = dict(observed_at=now.isoformat(), method='macOS registry read',
                   device_commands_sent=False,
                   devices=[summarize(n, payloads) for n in selected])
    output = ROOT / 'build/hardware' / now.strftime('%Y%m%dT%H%M%S.%fZ')
    output.mkdir(parents=True)
    raw = json.dumps(clean(selected), indent=2) + '\n'
    (output / 'target-registry.json').write_text(raw)
    summary['target_registry_sha256'] = sha256(raw.encode())
    summary['tool_sha256'] = sha256((ROOT / 'tools/inspect_usb.py').read_bytes())
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    print(f'Local evidence: {output}')


if __name__ == '__main__':
    main()
