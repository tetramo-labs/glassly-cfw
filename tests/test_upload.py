import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import urllib.error

from glassly_flasher import __version__, upload


class Opener:
    """Answers the first call with `first` (an exception or a report id), later calls with `then`."""

    def __init__(self, first, then='rep_OK'):
        self.answers = [first, then]
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        body = json.dumps({'reportId': answer}).encode()
        response = mock.MagicMock()
        response.__enter__.return_value = io.BytesIO(body)
        return response

    def bodies(self):
        return [json.loads(r.data.decode()) for r in self.requests]


def http_error(code):
    return urllib.error.HTTPError('https://core.test/api/tools/reports', code, 'refused', {}, io.BytesIO(b''))


class CollectTests(unittest.TestCase):
    def folder(self):
        self.tmp = tempfile.TemporaryDirectory()
        folder = Path(self.tmp.name)
        (folder / 'operation.log').write_text('MemoMind One: install\nConnecting to the glasses\n')
        (folder / 'device-info.json').write_text('{"model": "H001Y"}')
        (folder / 'flash-pass1.bin').write_bytes(b'\xff' * 64)
        (folder / 'trace.jsonl').write_text(''.join(f'{{"t": {i}}}\n' for i in range(200)))
        return folder

    def test_transcript_records_and_trace_tail_in_order(self):
        folder = self.folder()
        transcript = [(1000, 'status', 'Starting'), (2000, 'log', 'Paired glasses: MemoMind One (AA)')]
        with mock.patch.object(upload, 'MAX_TRACE_BYTES', 120):
            entries = upload.collect(folder, transcript)
        self.assertEqual([e['message'] for e in entries[:2]], ['Starting', 'Paired glasses: MemoMind One (AA)'])
        self.assertEqual(entries[0]['level'], 'status')
        self.assertEqual(entries[2], {'timestamp': entries[2]['timestamp'], 'level': 'info',
                                      'message': 'device-info.json: {"model": "H001Y"}', 'source': 'file'})
        trace = [e for e in entries if e.get('source') == 'trace']
        self.assertRegex(trace[0]['message'], r'trace.jsonl: \d+ bytes; the last \d+ rows follow')
        self.assertEqual(trace[-1]['message'], '{"t": 199}')
        self.assertTrue(all(json.loads(e['message'])['t'] > 180 for e in trace[1:]))
        self.assertFalse(any('flash-pass1' in e['message'] for e in entries))

    def test_operation_log_stands_in_for_a_missing_transcript(self):
        folder = self.folder()
        entries = upload.collect(folder, [])
        self.assertEqual([e['message'] for e in entries[:2]], ['MemoMind One: install', 'Connecting to the glasses'])

    def test_no_folder_gives_the_transcript_only(self):
        self.assertEqual([e['message'] for e in upload.collect(None, [(1, 'log', 'x')])], ['x'])
        self.assertEqual(upload.collect(Path('/nonexistent/folder'), []), [])


class SubmitTests(unittest.TestCase):
    def test_posts_the_report_as_this_tool(self):
        opener = Opener('rep_01ABC')
        entries = [upload.entry(1, 'hello'), upload.entry(2, '{"t": 1}', source='trace')]
        report = upload.submit(entries, {'session': {'device': 'memomind'}}, 'MemoMind One install: log upload', opener)
        self.assertEqual(report, 'rep_01ABC')
        request = opener.requests[0]
        self.assertEqual(request.full_url, f'{upload.CORE_URL}/api/tools/reports')
        self.assertEqual(request.get_method(), 'POST')
        self.assertEqual(request.get_header('User-agent'), f'glassly-cfw-flasher/{__version__}')
        body = opener.bodies()[0]
        self.assertEqual(body['tool']['name'], 'cfw_flasher')
        self.assertEqual(body['tool']['version'], __version__)
        self.assertEqual(body['reason'], 'log_upload')
        self.assertEqual(body['report'], {'actualBehavior': 'MemoMind One install: log upload'})
        self.assertEqual(body['context'], {'session': {'device': 'memomind'}})
        self.assertEqual(body['logs'], entries)

    def test_a_413_drops_the_trace_and_sends_once_more(self):
        opener = Opener(http_error(413), 'rep_SMALL')
        entries = [upload.entry(1, 'hello'), upload.entry(2, 'row', source='trace')]
        self.assertEqual(upload.submit(entries, {}, 'x', opener), 'rep_SMALL')
        self.assertEqual([len(b['logs']) for b in opener.bodies()], [2, 1])
        self.assertEqual(opener.bodies()[1]['logs'][0]['message'], 'hello')
        with self.assertRaises(upload.UploadError):
            upload.submit([upload.entry(1, 'hello')], {}, 'x', Opener(http_error(413), http_error(413)))

    def test_refusals_and_outages_become_messages(self):
        with self.assertRaises(upload.UploadError) as refused:
            upload.submit([], {}, 'x', Opener(http_error(429), http_error(429)))
        self.assertIn('last hour', refused.exception.args[1])
        with self.assertRaises(upload.UploadError) as down:
            upload.submit([], {}, 'x', Opener(urllib.error.URLError('no route'), urllib.error.URLError('no route')))
        self.assertIn('Could not reach', down.exception.args[1])
        with self.assertRaises(upload.UploadError):
            upload.submit([], {}, 'x', Opener(http_error(500), http_error(500)))


if __name__ == '__main__':
    unittest.main()
