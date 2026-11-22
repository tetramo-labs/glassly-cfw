"""MemoMind One (H001Y, H001F): install Glassly CFW revision 27 or put the official 1.0.3.127 firmware back through the
stock Bluetooth Classic updater, or record the glasses' identity.

Ported from glassly-memomind-one-cfw at e56172a3: `memomind install` (swift/MemoMindKit/Sources/memomind/
Install.swift and runLive in main.swift), which flashed revision 25 on 2026-11-11
(analysis/ble-link-20261110/flash-25-01). The sequence is the same: a read-only session for identity and installed
version, eight seconds apart a second session that repeats the identity check, sends the pre-update notice and runs
the updater on the OTA service, then read-only sessions until the expected firmware answers. The bundled revision 27
(glassly-memomind-one-cfw@ddc670f2) and the vendor's 1.0.3.127 image were both flashed by this tool on 2026-11-16
(glassly-memomind-one-cfw analysis/latency-20261114/flash-27-01).

There is no firmware backup: the stock firmware cannot read its flash back.
"""
import json
import os
import time

from ..base import FlashError
from . import rfcomm
from .image import CFW_REVISION, CFW_SHA256, STOCK_SHA256, STOCK_VERSION, load_cfw, load_stock
from .protocol import (GmSession, OtaTransaction, ProtocolError, check_identity, describe_identity,
                       installed_revision, is_known_kind)

WAIT_SECONDS = 600
FLASH_CONNECT_SECONDS = 120
BOOT_SECONDS = 300
SESSION_SPACING = 8
INQUIRY_SECONDS = 10
IDENTITY_KEYS = ('model', 'hver', 'fver', 'ver', 'mac', 'sn')
NO_FLASH_READ = ('The MemoMind One firmware has no command that reads its flash back, so this backup holds the '
                 "glasses' identity and capabilities only, not a firmware image.")


def describe_installed(version, revision):
    return f'official firmware {version}' if revision is None else f'GLASSLYCFW/{revision}'


class Session:
    def __init__(self, radio, output, reporter, trace):
        self.radio = radio
        self.output = output
        self.reporter = reporter
        self.trace = trace

    def record(self, **row):
        self.trace.write(json.dumps({'t': round(time.monotonic(), 6), **row}) + '\n')
        self.trace.flush()

    def save(self, name, document):
        with (self.output / name).open('x') as f:
            f.write(json.dumps(document, indent=2) + '\n')
            f.flush()
            os.fsync(f.fileno())

    def open(self, address, service, name):
        self.record(event='connect', session=name, service=f'{rfcomm.SERVICES[service]:04x}')
        channel = self.radio.connect(address, service)
        self.record(event='connected', session=name, channel=getattr(channel, 'channel_id', None),
                    source=getattr(channel, 'source', None))
        return rfcomm.TracedChannel(channel, self.trace, name)

    def find_glasses(self):
        """A pair of glasses this computer already knows, else the one pair answering a Bluetooth Classic
        search; the search repeats until the glasses answer or the wait runs out."""
        self.reporter.status('Looking for the glasses (switch them on and keep them close)')
        deadline = self.radio.monotonic() + WAIT_SECONDS
        hinted = False
        while True:
            self.reporter.check_cancel()
            paired = self.radio.paired()
            glasses = rfcomm.select_glasses(paired)
            if glasses is not None:
                self.reporter.log(f'Glasses paired with this computer: {glasses.name} ({glasses.address}).')
                if glasses.classic is False:
                    self.reporter.log('That pairing is the glasses\' Bluetooth LE side, which may not carry their '
                                      'Classic address; if it does not answer, the flasher searches for them itself.')
                return glasses
            try:
                found = [d for d in self.radio.discover(INQUIRY_SECONDS) if rfcomm.is_glasses(d)]
            except rfcomm.LinkError as e:
                found = []
                if not hinted:
                    self.reporter.log(f'The search failed: {e}')
            self.record(event='inquiry', devices=[[d.address, d.name] for d in found])
            if len(found) > 1:
                raise FlashError(f'More than one pair of MemoMind glasses answered: {rfcomm.describe(found)}. Switch '
                                 'the others off and start again. Nothing was written.')
            if found:
                self.reporter.log(f'Glasses found: {found[0].name} ({found[0].address}).')
                return found[0]
            if self.radio.monotonic() > deadline:
                raise FlashError('No MemoMind glasses answered. Switch them on, forget them on their phone, hold the '
                                 'button after pressing it five times to reset them, and start again. Nothing was '
                                 'written.')
            if not hinted:
                self.reporter.log('No MemoMind glasses yet; the flasher keeps looking.')
                hinted = True
            self.radio.sleep(2)

    def query(self, address, name):
        """Read-only: heartbeat, device information and, for the known kind, the capabilities query."""
        channel = self.open(address, 'normal', name)
        try:
            session = GmSession(channel, timeout=5)
            device = session.probe()
            return device, session.capabilities() if is_known_kind(device) else None
        finally:
            channel.close()

    def search(self, glasses):
        """A Classic inquiry for the glasses, for when the paired record's address does not answer."""
        self.reporter.log('Searching for the glasses over Bluetooth Classic.')
        try:
            found = [d for d in self.radio.discover(INQUIRY_SECONDS) if rfcomm.is_glasses(d)]
        except rfcomm.LinkError as e:
            self.reporter.log(f'The search failed: {e}')
            return glasses
        self.record(event='inquiry', devices=[[d.address, d.name] for d in found])
        if not found:
            self.reporter.log('No MemoMind glasses answered the search.')
            return glasses
        if any(d.address == glasses.address for d in found) or len(found) > 1:
            self.reporter.log(f'The search found {rfcomm.describe(found)}.')
            return glasses
        self.reporter.log(f'The search found {found[0].name} ({found[0].address}); connecting to that address '
                          f'instead of the paired {glasses.address}.')
        return found[0]

    def inspect(self, glasses):
        self.reporter.status('Connecting to the glasses (switch them on and keep them close)')
        deadline = self.radio.monotonic() + WAIT_SECONDS
        failures = 0
        while True:
            self.reporter.check_cancel()
            try:
                device, tlvs = self.query(glasses.address, 'inspect')
                break
            except (rfcomm.LinkError, TimeoutError) as e:
                if self.radio.monotonic() > deadline:
                    raise FlashError(f'Could not read the glasses: {e}. Check that they are switched on, charged and '
                                     'close to this computer. Nothing was written.') from e
                failures += 1
                self.reporter.status(f'Connecting to the glasses again: {e}')
                self.reporter.log('Are the glasses switched on and close, and is Bluetooth off on their phone?')
                if failures % 4 == 1:
                    glasses = self.search(glasses)
            self.radio.sleep(SESSION_SPACING)
        self.reporter.log(f'Glasses report {describe_identity(device)}.')
        self.save('device-info.json', device)
        if tlvs is not None:
            if tlvs == [(6, b'\x02')]:
                capabilities = {'status': 2, 'meaning': 'official firmware: no Glassly capabilities'}
            else:
                documents = [v for k, v in tlvs if k == 5]
                try:
                    capabilities = json.loads(documents[0].rstrip(b'\0')) if len(documents) == 1 else None
                except ValueError:
                    capabilities = None
                capabilities = capabilities or {'tlvs': [[k, v.hex()] for k, v in tlvs]}
            self.save('capabilities.json', capabilities)
        return device, tlvs, glasses

    def backup(self):
        glasses = self.find_glasses()
        device, tlvs, glasses = self.inspect(glasses)
        installed = describe_installed(device.get('ver'), installed_revision(tlvs)) if tlvs is not None \
            else 'not queried'
        self.reporter.log(f'Installed: {installed}.')
        self.reporter.log(NO_FLASH_READ)
        self.reporter.log('Nothing was written.')
        return {'mode': 'backup', 'address': glasses.address, 'name': glasses.name, 'device': device,
                'installed': installed, 'flash_modified': False, 'firmware_image_saved': False, 'note': NO_FLASH_READ}

    def connect_for_update(self, address, expected):
        """Opens the update session's normal channel and repeats the identity check. Read-only, so a failed
        connection is tried again; the glasses refuse a session opened right after another one closed."""
        deadline = self.radio.monotonic() + FLASH_CONNECT_SECONDS
        while True:
            try:
                channel = self.open(address, 'normal', 'control')
            except rfcomm.LinkError as e:
                error = e
            else:
                try:
                    session = GmSession(channel)
                    device = session.probe()
                    check_identity(device, address)
                    changed = [k for k in IDENTITY_KEYS if device.get(k) != expected.get(k)]
                    if changed:
                        raise FlashError(f'The glasses reported a different {", ".join(changed)} on the update '
                                         f'connection ({describe_identity(device)}). Nothing was written.')
                    return channel, session, device
                except (rfcomm.LinkError, TimeoutError) as e:
                    channel.close()
                    error = e
                except BaseException:
                    channel.close()
                    raise
            if self.radio.monotonic() > deadline:
                raise FlashError(f'Could not connect to the glasses for the update: {error}. Nothing was written.') \
                    from error
            self.reporter.log(f'The glasses did not take the update connection yet ({error}); trying again.')
            self.reporter.check_cancel()
            self.radio.sleep(SESSION_SPACING)

    def flash(self, address, image, expected, mode, goal):
        self.reporter.status('Connecting for the update')
        control, session, device = self.connect_for_update(address, expected)
        ota = transaction = None
        try:
            self.reporter.status(f'Sending {goal} (keep the glasses switched on and close)')
            session.notify_ota()
            ota = self.open(address, 'ota', 'ota')
            transaction = OtaTransaction(ota, image, device, address, check_control=control.drain,
                                         sleep=self.radio.sleep, progress=self.reporter.progress, log=self.reporter.log)
            return transaction.run()
        except (FlashError, TimeoutError) as e:
            if transaction is None or transaction.chunks == 0:
                raise FlashError(f'{e} No firmware bytes were sent; the glasses keep their current firmware.') from e
            if transaction.phase.startswith(('block', 'device pacing')):
                raise FlashError(f'{e} The glasses keep running their current firmware until a transfer completes. '
                                 f'Keep them charged and run {mode.capitalize()} again: it continues from where this '
                                 'transfer stopped if the glasses still hold it, otherwise it starts over.') from e
            raise FlashError(f'{e} Every block was sent but the update did not finish cleanly. Wait a minute, then '
                             'run Back up to see which firmware the glasses run, and keep this folder.') from e
        finally:
            if ota is not None:
                ota.close()
            control.close()

    def wait_for_boot(self, address):
        self.reporter.status('Waiting for the glasses to restart (wake them if the display stays dark)')
        deadline = self.radio.monotonic() + BOOT_SECONDS
        while True:
            self.radio.sleep(SESSION_SPACING)
            try:
                device, tlvs = self.query(address, 'boot-check')
            except (rfcomm.LinkError, TimeoutError, ProtocolError) as e:
                if self.radio.monotonic() > deadline:
                    raise FlashError('The firmware was transferred and the glasses acknowledged the restart, but they '
                                     f'did not answer within {BOOT_SECONDS // 60} minutes ({e}). Wake them, then run '
                                     'Back up to see which firmware they run.') from e
                continue
            if tlvs is None:
                raise FlashError(f'After the restart the glasses reported {describe_identity(device)}.')
            return describe_installed(device.get('ver'), installed_revision(tlvs))

    def update(self, mode, image, target, image_sha256):
        """Takes the glasses to `target`: CFW_REVISION for install, None (official firmware) for restore."""
        glasses = self.find_glasses()
        device, tlvs, glasses = self.inspect(glasses)
        check_identity(device, glasses.address)
        installed = describe_installed(device.get('ver'), installed_revision(tlvs))
        goal = describe_installed(STOCK_VERSION, target)
        summary = {'mode': mode, 'address': glasses.address, 'name': glasses.name, 'device': device,
                   'installed_before': installed, 'image_sha256': image_sha256}
        if installed == goal:
            self.reporter.log(f'{goal} is already installed. Nothing was written.')
            return {**summary, 'state': 'already installed', 'flash_modified': False}
        self.reporter.log(f'The glasses run {installed}; sending {goal}.')
        self.reporter.status('Preparing the update')
        self.radio.sleep(SESSION_SPACING)
        self.reporter.check_cancel()
        result = self.flash(glasses.address, image, device, mode, goal)
        self.reporter.log(f'Reboot acknowledged after {result["blocks"]} blocks ({result["chunks"]} chunks).')
        booted = self.wait_for_boot(glasses.address)
        if booted != goal:
            raise FlashError(f'The glasses restarted on {booted} instead of {goal}. Keep this folder and open an issue.')
        self.reporter.log(f'The glasses answered as {goal}.')
        return {**summary, **result, 'state': 'installed' if mode == 'install' else 'restored', 'flash_modified': True,
                'reboot_acknowledged': True, 'booted_version': goal, 'post_reboot_version_verified': True}


def run(mode, output, reporter, link=None):
    if mode not in ('install', 'restore', 'backup'):
        raise FlashError(f'MemoMind One does not support {mode}')
    image = {'install': load_cfw, 'restore': load_stock}[mode]() if mode != 'backup' else None
    radio = link or rfcomm.open_radio()
    reporter.check_cancel()
    with (output / 'trace.jsonl').open('x') as trace:
        session = Session(radio, output, reporter, trace)
        try:
            if mode == 'backup':
                return session.backup()
            if mode == 'install':
                return session.update(mode, image, CFW_REVISION, CFW_SHA256)
            return session.update(mode, image, None, STOCK_SHA256)
        except TimeoutError as e:
            raise FlashError(f'The glasses stopped answering: {e}') from e
