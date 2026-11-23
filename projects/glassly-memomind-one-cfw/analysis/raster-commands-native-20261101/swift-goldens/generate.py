import ctypes,hashlib,json,re,subprocess
from pathlib import Path
root=Path.cwd()
c=ctypes.CDLL('/tmp/mm-swift-raster-goldens/rle.dylib')
class Surface(ctypes.Structure):
 _fields_=[('pixels',ctypes.POINTER(ctypes.c_ubyte)),('bytes',ctypes.c_size_t),('rowbytes',ctypes.c_uint32),('rows',ctypes.c_uint32),('stride',ctypes.c_uint32)]
c.mm_rle_encode.argtypes=[ctypes.POINTER(Surface),ctypes.POINTER(ctypes.c_ubyte),ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
def packed(nibbles):return bytes((nibbles[i]<<4)|nibbles[i+1] for i in range(0,len(nibbles),2))
def enc(raw,rowbytes,rows,stride):
 inp=(ctypes.c_ubyte*len(raw)).from_buffer_copy(raw);out=(ctypes.c_ubyte*(rowbytes*rows*2))();n=ctypes.c_size_t()
 s=Surface(inp,len(raw),rowbytes,rows,stride)
 assert c.mm_rle_encode(ctypes.byref(s),out,len(out),ctypes.byref(n))==0
 return bytes(out[:n.value])
cases=[]
counts=list(range(1,17))+[17,254,255,256,257,65534,65535,65536,131070,131071]
for count in counts:
 raw=packed([5]*count+[10]*(210000-count));cases.append((f'run{count}',raw,enc(raw,300,350,300)))
for color in range(16):
 raw=bytes([color*17])*105000;cases.append((f'color{color}',raw,enc(raw,300,350,300)))
bbox=packed([0]*15+[1]*16+[2]*17)
cases.append(('crossrow',bbox,enc(bbox,6,4,6)))
src=Path('tests/g2_compat/upstream/demos/video-bench.ts').read_text();fn=re.search(r'function rleEncode\(.*?\n}',src,re.S).group()
Path('/tmp/mm-swift-raster-goldens/original.ts').write_text('import fs from "node:fs";\n'+fn+'\nconst rows = JSON.parse(fs.readFileSync(0,"utf8"));\nprocess.stdout.write(JSON.stringify(rows.map((x: string) => Buffer.from(rleEncode(Buffer.from(x,"hex"))).toString("hex"))));\n')
# Full independently extracted original TypeScript function, executed with Node's type erasure.
p=subprocess.run(['node','--experimental-strip-types','/tmp/mm-swift-raster-goldens/original.ts'],input=json.dumps([r.hex() for _,r,_ in cases]),text=True,capture_output=True,check=True)
js=json.loads(p.stdout)
assert js==[out.hex() for _,_,out in cases]
lines=['// SPDX-License-Identifier: MIT','// Offline dual reference: compiled portable C mm_rle_encode AND unmodified', '// extracted G2 TypeScript rleEncode executed with Node22 --experimental-strip-types.', '// Both independently agreed for every fixture. No Python/C/Node execution in Swift tests.', '// G2 revision1a6db4fd75de202a96599cc8f9f12fa721e7c3ce. License: LICENSE.']
for name in ['tests/g2_compat/upstream/demos/video-bench.ts','tests/g2_compat/upstream/patches/zlib_glue.c','runtime/portable/rle.c']:
 lines.append('// '+name+' SHA256 '+hashlib.sha256(Path(name).read_bytes()).hexdigest())
lines+=['enum RasterReferenceVectors {','    static let runs: [(count: Int, rleHex: String)] = [']
for n,(_,_,data) in zip(counts,cases):lines.append(f'        ({n}, "{data.hex()}"),')
lines+=['    ]','    static let colors: [String] = [']
for _,_,data in cases[len(counts):-1]:lines.append(f'        "{data.hex()}",')
lines+=['    ]',f'    static let crossRow = "{cases[-1][2].hex()}"','}','']
Path('swift/MemoMindKit/Tests/MemoMindCoreTests/RasterReferenceVectors.swift').write_text('\n'.join(lines))
print('C and original TypeScript exact agreement:',len(cases),'vectors')
