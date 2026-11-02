import runpy,hashlib,json,subprocess
from pathlib import Path
m=runpy.run_path('/tmp/mm-swift-raster-goldens/generate.py');enc=m['enc'];packed=m['packed']
rows=[]
for count in (8175,8176,8169,8170):
 raw=packed([i%2 for i in range(count)]+[2]*(210000-count));rle=enc(raw,300,350,300);rows.append((raw,rle))
p=subprocess.run(['node','--experimental-strip-types','/tmp/mm-swift-raster-goldens/original.ts'],input=json.dumps([raw.hex() for raw,_ in rows]),text=True,capture_output=True,check=True)
assert json.loads(p.stdout)==[rle.hex() for _,rle in rows]
full=bytes([6])+rows[0][1];box=bytes([3,0,0,150,175,0xcd,0xab])+rows[2][1]
assert len(full)==len(box)==8192
assert 1+len(rows[1][1])==7+len(rows[3][1])==8193
p=Path('swift/MemoMindKit/Tests/MemoMindCoreTests/RasterReferenceVectors.swift')
p.write_text(p.read_text()+f'\nextension RasterReferenceVectors {{\n    static let capacityFullSHA256 = "{hashlib.sha256(full).hexdigest()}"\n    static let capacityBoxSHA256 = "{hashlib.sha256(box).hexdigest()}"\n}}\n')
print('Four capacity fixtures also agree; exact command boundaries8192/8193.')
