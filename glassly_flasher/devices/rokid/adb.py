from pathlib import Path
import re
import shutil
import subprocess
import sys

from ... import paths
from ..base import FlashError

NOT_ALLOWED = 'not allow cmd'


def find():
    exe = 'adb.exe' if sys.platform == 'win32' else 'adb'
    bundled = paths.resource('third_party/platform-tools') / sys.platform / exe
    if bundled.is_file():
        return str(bundled)
    found = shutil.which('adb')
    if found:
        return found
    # An app opened from Finder gets a bare PATH, without Homebrew or the Android SDK.
    for candidate in ('/opt/homebrew/bin/adb', '/usr/local/bin/adb',
                      Path.home() / 'Library/Android/sdk/platform-tools/adb',
                      Path.home() / 'Android/Sdk/platform-tools/adb'):
        if Path(candidate).is_file():
            return str(candidate)
    raise FlashError('adb was not found. Install Android platform-tools (https://developer.android.com/tools/releases/'
                     'platform-tools) or use a flasher build that bundles it.')


class Adb:
    def __init__(self, path, runner=subprocess.run):
        self.path = path
        self.serial = None
        self.runner = runner

    def run(self, *args, timeout=60, check=True):
        command = [self.path, *(['-s', self.serial] if self.serial else []), *args]
        try:
            done = self.runner(command, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise FlashError(f'adb {" ".join(args)} did not answer within {timeout} s') from e
        output = (done.stdout or '') + (done.stderr or '')
        if check and done.returncode != 0:
            raise FlashError(f'adb {" ".join(args)} failed: {output.strip() or f"exit {done.returncode}"}')
        return output

    def shell(self, command, timeout=60, check=True):
        output = self.run('shell', command, timeout=timeout, check=check)
        # Rokid's adbd refuses pm, cmd, dumpsys and logcat once its assistant sets persist.vendor.adb=false.
        if NOT_ALLOWED in output:
            raise FlashError('The glasses refused the command ("RKD-- not allow cmd"). Their Rokid assistant has '
                             'locked debugging. Restart the glasses and try again; if it persists, report this with '
                             'the backup folder.')
        return output

    def version(self):
        return self.run('version', check=False).splitlines()[0:2]

    def devices(self):
        """[(serial, state, {property: value})] for every device adb sees."""
        rows = []
        for line in self.run('devices', '-l', check=False).splitlines()[1:]:
            parts = line.split()
            if len(parts) < 2:
                continue
            props = dict(part.split(':', 1) for part in parts[2:] if ':' in part)
            rows.append((parts[0], parts[1], props))
        return rows

    def getprop(self, name):
        return self.shell(f'getprop {name}').strip()

    def mdns(self, service_type):
        """Host:port of every advertised service of `service_type` (for example `_adb-tls-pairing._tcp`)."""
        found = []
        for line in self.run('mdns', 'services', check=False).splitlines():
            if service_type in line:
                match = re.search(r'(\d+\.\d+\.\d+\.\d+:\d+)', line)
                if match:
                    found.append(match.group(1))
        return found

    def pair(self, address, code):
        output = self.run('pair', address, code, timeout=30, check=False)
        if 'Successfully paired' not in output:
            raise FlashError(f'Pairing with {address} failed: {output.strip()}. Check the code on the glasses and '
                             'that they are on the same Wi-Fi as this computer.')
        return output

    def connect(self, address):
        output = self.run('connect', address, timeout=30, check=False)
        if 'connected to' not in output:
            raise FlashError(f'Could not connect to {address}: {output.strip()}')
        return output
