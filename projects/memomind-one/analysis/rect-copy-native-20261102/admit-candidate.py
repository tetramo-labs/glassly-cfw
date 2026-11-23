"""Offline exact reconstruction and literal Swift catalog/test admission; no device actions."""
if not __debug__:
    raise RuntimeError('Verification requires Python assertions; optimized execution is refused')
from pathlib import Path
import json,sys,hashlib
sys.path.insert(0,str(Path('scripts').resolve()))
from build_memomind_flash_canary import verify_canary
from memomind_ota import unpack_ota
root=Path('analysis/rect-copy-native-20261102');firmware=Path('captures/firmware/rect-copy-001')
def sha(b):return hashlib.sha256(b).hexdigest()
image=(firmware/'firmware.bin').read_bytes();blob=Path('runtime/build/rect-copy-001/graphics.bin').read_bytes()
manifest=json.loads((firmware/'manifest.json').read_text());proof=json.loads((firmware/'verification.json').read_text())
reproduced,reproof=verify_canary(Path('captures/firmware/ota-1.0.3.127-glassly-text.bin').read_bytes(),blob,manifest)
assert image==reproduced and proof==reproof
info,streams=unpack_ota(image);old,oldstreams=unpack_ota(Path('captures/firmware/raster-commands-001/firmware.bin').read_bytes())
assert all(streams[i]['packed']==oldstreams[i]['packed'] for i in (1,2,4,5,6))
assert (firmware/'expected-app-header.bin').read_bytes()==streams[3]['raw'][:256]
pins={'image_sha256':sha(image),'image_bytes':len(image),'runtime_sha256':sha(blob),'runtime_bytes':len(blob),'header_sha256':sha(image[:150]),'app_header_sha256':sha(streams[3]['raw'][:256]),'metadata_packed_bytes':len(streams[0]['packed']),'metadata_sha256':sha(streams[0]['packed']),'app_packed_bytes':len(streams[3]['packed']),'app_raw_bytes':len(streams[3]['raw']),'app_sha256':sha(streams[3]['packed'])}
(root/'candidate-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
(root/'candidate-reconstruction.json').write_text(json.dumps({'format':'memomind-rect-copy-offline-reconstruction-v1','release':'rect-copy-001','pins':pins,'complete_reconstruction_matches':True,'construction_proof_matches':True,'unchanged_packed_components':[1,2,4,5,6],'decoded_validation':info,'hardware_tested':False},indent=2)+'\n')
p=Path('swift/MemoMindKit/Sources/MemoMindCore/FirmwareImage.swift');s=p.read_text();assert 'name: "rect-copy-001"' not in s
entry=f'''        // Exact reconstructed mode9 release; admission alone is not boot proof.
        FirmwareRelease(name: "rect-copy-001",
                        sha256: "{pins['image_sha256']}",
                        byteCount: {len(image)}, modified: true, profile: "H001Y-1.0.3.127-flash-canary-v1",
                        headerSHA256: "{pins['header_sha256']}",
                        streams: streamPins(.rectCopy)),
'''
marker='    ]\n\n    private enum StreamVariant';assert marker in s;s=s.replace(marker,entry+marker)
s=s.replace('case stock, reader, canary, raster }','case stock, reader, canary, raster, rectCopy }')
marker='''        }
        let sizes: [Int]''';assert marker in s
s=s.replace(marker,f'''        case .rectCopy:
            metadata = {len(streams[0]['packed'])}; appPacked = {pins['app_packed_bytes']}; appRaw = {pins['app_raw_bytes']}
            metadataHash = "{pins['metadata_sha256']}"
            appHash = "{pins['app_sha256']}"
'''+marker);catalog_path=p;catalog_text=s
p=Path('swift/MemoMindKit/Tests/MemoMindCoreTests/FirmwareImageTests.swift');s=p.read_text()
s=s.replace('    /// Fixtures are required',f'    private let rectCopySHA = "{pins["image_sha256"]}"\n\n    /// Fixtures are required',1)
a=s.index('    func testRequiredActualReviewedOfflineRasterFixture()');b=s.index('    func testInvalidOrUntrustedExpectedDigestCannotExpandCatalog()',a)
block=s[a:b].replace('OfflineRasterFixture','OfflineRectCopyFixture').replace('testRasterEligibility','testRectCopyEligibility').replace('rasterSHA','rectCopySHA').replace('raster-commands-001','rect-copy-001')
for oldv,newv in [('2_227_971',str(len(image))),('61392',str(len(blob))),('956_869',str(pins['app_packed_bytes'])),('1_834_608',str(pins['app_raw_bytes'])),('5c86bd35693aba72250297f0e63fc568579d6f572cc3a1a93d7eaa3d9f65f85c',pins['header_sha256']),('07c6f9bb617f88b29367641c0abdfbd669e62710449a0b8c0c88eba41d4c62c2',pins['metadata_sha256']),('750f7970025f86d4721ce3095139121254ca7969577f0fbbe5020eb22bb18cc3',pins['app_sha256'])]:block=block.replace(oldv,newv)
s=s[:b]+block+s[b:]
assert 'case .rectCopy:' in catalog_text and s.count('func testRequiredActualReviewedOfflineRectCopyFixture()')==1
catalog_path.write_text(catalog_text);p.write_text(s)
for template in root.glob('*.in'):
 text=template.read_text().replace('@IMAGE_SHA@',pins['image_sha256']).replace('@HEADER_SHA@',pins['app_header_sha256']).replace('@IMAGE_BYTES@',str(len(image)))
 assert '@IMAGE_' not in text and '@HEADER_' not in text
 template.with_suffix('').write_text(text)
print(json.dumps(pins,indent=2))
