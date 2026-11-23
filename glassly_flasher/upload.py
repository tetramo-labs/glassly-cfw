"""Sends a session's log to the Glassly reports system: one POST /api/tools/reports with the transcript the GUI
collected, the session folder's small JSON records and the tail of its protocol trace, filed as a bug report whose
trigger source is this tool. Nothing from a firmware backup (the .bin files) is sent. The report id comes back for
the user to quote."""
import json
import os
import platform
import ssl
import sys
import time
import urllib.error
import urllib.request

from . import __version__

CORE_URL = os.environ.get('GLASSLY_CORE_URL', 'https://core.glassly.ai').rstrip('/')
TOOL = 'cfw_flasher'
MAX_JSON_BYTES = 256 * 1024
MAX_TRACE_BYTES = 1 << 20
MAX_ENTRIES = 20_000
TIMEOUT_SECONDS = 60


class UploadError(Exception):
    pass


def entry(timestamp_ms, message, level='info', source=None):
    row = {'timestamp': int(timestamp_ms), 'level': level, 'message': message}
    if source:
        row['source'] = source
    return row


def collect(output, transcript):
    """Log entries for a session: the GUI's transcript (time, kind, text), else the folder's operation.log, then
    the JSON records and the end of trace.jsonl."""
    entries = []
    if transcript:
        for stamp, kind, text in transcript:
            entries.append(entry(stamp, text, 'status' if kind == 'status' else 'info'))
    elif output is not None and (output / 'operation.log').is_file():
        log = output / 'operation.log'
        stamp = int(log.stat().st_mtime * 1000)
        for line in log.read_text('utf-8', 'replace').splitlines():
            if line.strip():
                entries.append(entry(stamp, line))
    if output is None or not output.is_dir():
        return entries
    for path in sorted(output.glob('*.json')):
        if path.stat().st_size <= MAX_JSON_BYTES:
            entries.append(entry(path.stat().st_mtime * 1000, f'{path.name}: {path.read_text("utf-8", "replace")}',
                                 source='file'))
    trace = output / 'trace.jsonl'
    if trace.is_file():
        with trace.open('rb') as f:
            size = f.seek(0, os.SEEK_END)
            f.seek(max(0, size - MAX_TRACE_BYTES))
            tail = f.read().decode('utf-8', 'replace')
        lines = tail.splitlines()
        if size > MAX_TRACE_BYTES and lines:
            lines = lines[1:]
            entries.append(entry(trace.stat().st_mtime * 1000, f'trace.jsonl: {size} bytes; the last {len(lines)} rows follow',
                                 source='trace'))
        stamp = trace.stat().st_mtime * 1000
        for line in lines:
            if line.strip():
                entries.append(entry(stamp, line, source='trace'))
    return entries[-MAX_ENTRIES:]


def context(device_key, mode, output):
    return {
        'session': {'device': device_key, 'mode': mode, 'folder': output.name if output is not None else None},
        'host': {'platform': sys.platform, 'release': platform.platform(), 'python': platform.python_version()},
    }


def ssl_context():
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def submit(entries, session_context, description, opener=None):
    """Files the report; on a 413 the trace rows are dropped and it is sent once more."""
    body = {
        'tool': {'name': TOOL, 'version': __version__, 'platform': platform.platform()},
        'reason': 'log_upload',
        'report': {'actualBehavior': description},
        'context': session_context,
        'logs': entries,
    }
    try:
        return post(body, opener)
    except UploadError as e:
        if e.args and e.args[0] == 413 and any(row.get('source') == 'trace' for row in entries):
            body['logs'] = [row for row in entries if row.get('source') != 'trace']
            return post(body, opener)
        raise


def post(body, opener=None):
    data = json.dumps(body).encode('utf-8')
    request = urllib.request.Request(f'{CORE_URL}/api/tools/reports', data=data, method='POST', headers={
        'content-type': 'application/json', 'user-agent': f'glassly-flash-tool/{__version__}'})
    try:
        with (opener or default_opener)(request) as response:
            reply = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 413:
            raise UploadError(413, 'The log is too large for one upload.') from e
        if e.code == 429:
            raise UploadError(429, 'Too many uploads from this network in the last hour; try again later.') from e
        raise UploadError(e.code, f'The Glassly server refused the upload (HTTP {e.code}).') from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise UploadError(0, f'Could not reach the Glassly server: {getattr(e, "reason", e)}') from e
    report_id = reply.get('reportId') if isinstance(reply, dict) else None
    if not isinstance(report_id, str) or not report_id:
        raise UploadError(0, 'The Glassly server did not return a report id.')
    return report_id


def default_opener(request):
    return urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=ssl_context())


def now_ms():
    return int(time.time() * 1000)
