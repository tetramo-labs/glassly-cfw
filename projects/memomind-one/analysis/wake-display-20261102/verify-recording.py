#!/usr/bin/env python3
import ctypes
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import struct
import wave

root = Path(__file__).resolve().parents[2]
capture = Path(sys.argv[1])
codec = root/'.tools/memomind-open-platform/GlassSDK/docs/examples/bluetooth_wire.py'
spec = importlib.util.spec_from_file_location('reference', codec)
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)
trace = (capture/'trace.jsonl').read_bytes()
rows = [json.loads(line) for line in trace.splitlines()]
wire = b''.join(bytes.fromhex(r['hex']) for r in rows if r['event']=='receive' and r.get('session')=='recording')
frames = []
controls = []
packets = 0
while wire:
    assert wire[0] == 0x52
    if wire[1] in (0x11, 0x13):
        assert len(wire) >= 6
        controls.append(wire[:6].hex())
        wire = wire[6:]
        continue
    assert len(wire) >= 12
    size = 12 + wire[6]*49
    command, decoded = reference.parse_record_packet(wire[:size], 0)
    assert command == 0x92
    frames.extend(decoded)
    packets += 1
    wire = wire[size:]
logged = [bytes.fromhex(p) for r in rows if r['event']=='opus-frames' for p in r['packetsHex']]
assert frames == logged and frames
lib = ctypes.CDLL('/opt/homebrew/lib/libopus.dylib')
lib.opus_decoder_create.argtypes = [ctypes.c_int32,ctypes.c_int,ctypes.POINTER(ctypes.c_int)]
lib.opus_decoder_create.restype = ctypes.c_void_p
lib.opus_decode.argtypes = [ctypes.c_void_p,ctypes.c_char_p,ctypes.c_int32,ctypes.POINTER(ctypes.c_int16),ctypes.c_int,ctypes.c_int]
lib.opus_decode.restype = ctypes.c_int
lib.opus_packet_get_nb_channels.argtypes = [ctypes.c_char_p]
lib.opus_packet_get_nb_channels.restype = ctypes.c_int
lib.opus_decoder_destroy.argtypes = [ctypes.c_void_p]
error = ctypes.c_int()
decoder = lib.opus_decoder_create(16000,1,ctypes.byref(error))
assert decoder and not error.value
samples = []
channels = set()
try:
    for frame in frames:
        channels.add(lib.opus_packet_get_nb_channels(frame))
        output = (ctypes.c_int16*1920)()
        count = lib.opus_decode(decoder,frame,len(frame),output,1920,0)
        assert count == 320
        samples.extend(output[:count])
finally:
    lib.opus_decoder_destroy(decoder)
assert channels == {1}
stop = next(r for r in rows if r['event']=='microphone-stop-submitted')
complete = next(r for r in rows if r['event']=='operation-complete')
last = max(r['uptimeSeconds'] for r in rows if r['event']=='opus-frames')
if len(sys.argv) > 2:
    output = Path(sys.argv[2]).expanduser()
    with output.open('xb') as handle:
        with wave.open(handle, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(struct.pack('<'+'h'*len(samples), *samples))
report = {'result':'passed','capture':str(capture),'traceSHA256':hashlib.sha256(trace).hexdigest(),
          'referenceCodecSHA256':hashlib.sha256(codec.read_bytes()).hexdigest(),
          'rawReceiveMatchesSavedPackets':True,'controlHex':controls,'packets':packets,
          'opusFrames':len(frames),'packetChannels':sorted(channels),'outputSampleRate':16000,
          'samplesPerFrame':320,'sampleCount':len(samples),'decodedSeconds':len(samples)/16000,
          'peakAbsolutePCM':max(abs(n) for n in samples),
          'quietSecondsBeforeClose':complete['uptimeSeconds']-last,
          'stopDrainSeconds':complete['uptimeSeconds']-stop['uptimeSeconds'],
          'physicalAudioContentConfirmed':False,'stopAcknowledgmentExists':False,
          'losslessContinuityProven':False,'firmwareChanged':False}
print(json.dumps(report,indent=2))
