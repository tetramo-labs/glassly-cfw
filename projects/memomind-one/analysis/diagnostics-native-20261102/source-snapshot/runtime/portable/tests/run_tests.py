#!/usr/bin/env python3
"""Offline geometry/RLE tests; pinned reference sources, no device access."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--g2-source', type=Path, default=ROOT.parents[1] / 'tests/g2_compat/upstream')
    parser.add_argument('--output', type=Path, help='New output directory; defaults to temporary directory')
    parser.add_argument('--cc', default='clang')
    parser.add_argument('--rvcc', type=Path, default=ROOT.parents[1] / '.tools/riscv-toolchain/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-gcc')
    args = parser.parse_args()
    upstream = json.loads((ROOT/'UPSTREAM.json').read_text())
    g2 = args.g2_source.resolve()
    bundled = (ROOT.parents[1] / 'tests/g2_compat/upstream').resolve()
    revision = (json.loads((g2.parent/'UPSTREAM.json').read_text())['commit'] if g2 == bundled else
                subprocess.check_output(['git','-C',str(g2),'rev-parse','HEAD'],text=True).strip())
    if revision != upstream['source_commit']:
        raise RuntimeError('Reference checkout is not the pinned G2 commit')
    for name, digest in upstream['files'].items():
        if hashlib.sha256((g2/name).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Reference source hash mismatch: '+name)
    output = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix='memomind-geometry-'))
    if args.output:
        output.mkdir(parents=True,exist_ok=False)
    flags = ['-std=c11','-O1','-g','-Wall','-Wextra','-Wno-unused-function',
             '-fsanitize=address,undefined','-fno-sanitize-recover=all']
    build = [args.cc,*flags,'-I'+str(g2/'patches'),
             '-DG2_REFERENCE_SOURCE="'+str(g2/'patches/host/shapes_host_test.c')+'"',
             str(ROOT/'geometry.c'),str(ROOT/'tests/g2_reference.c'),str(ROOT/'tests/test_geometry.c'),
             '-o',str(output/'test_geometry')]
    built = subprocess.run(build,capture_output=True,text=True)
    (output/'build.stderr').write_text(built.stderr)
    built.check_returncode()
    result = subprocess.run([str(output/'test_geometry')],check=True,capture_output=True,text=True)
    (output/'test.stdout').write_text(result.stdout)
    (output/'test.stderr').write_text(result.stderr)
    rle_build = [args.cc,*flags,'-I'+str(g2/'patches'),
                 '-DG2_REFERENCE_SOURCE="'+str(g2/'patches/host/shapes_host_test.c')+'"',
                 '-DG2_RLE_REFERENCE_SOURCE="'+str(g2/'patches/rle.c')+'"',
                 str(ROOT/'rle.c'),str(ROOT/'tests/g2_rle_reference.c'),str(ROOT/'tests/test_rle.c'),
                 '-o',str(output/'test_rle')]
    built = subprocess.run(rle_build,capture_output=True,text=True)
    (output/'rle-build.stderr').write_text(built.stderr)
    built.check_returncode()
    rle_result = subprocess.run([str(output/'test_rle'),str(output/'encoder-cases.bin')],check=True,capture_output=True,text=True)
    (output/'rle-test.stdout').write_text(rle_result.stdout)
    (output/'rle-test.stderr').write_text(rle_result.stderr)
    # Extract the original pure TS encoder verbatim, avoiding its live demo entry.
    source=(g2/'demos/video-bench.ts').read_text()
    encoder=source[source.index('function rleEncode('):source.index('\n}\n',source.index('function rleEncode('))+3]
    script=encoder+"""
const bytes = new Uint8Array(await Bun.file(process.argv[2]!).arrayBuffer());
const dv = new DataView(bytes.buffer); let p=0, cases=0;
while(p<bytes.length) {
  const n=dv.getUint32(p,true), k=dv.getUint32(p+4,true); p+=8;
  const actual=rleEncode(bytes.subarray(p,p+n)); p+=n;
  const expected=bytes.subarray(p,p+k); p+=k;
  if(actual.length!==k || actual.some((v,i)=>v!==expected[i])) throw new Error(`encoder case ${cases} mismatch`);
  cases++;
}
console.log(`PASS: ${cases} byte-identical original TypeScript encoder cases`);
"""
    (output/'encoder-reference.ts').write_text(script)
    ts_result=subprocess.run(['bun',str(output/'encoder-reference.ts'),str(output/'encoder-cases.bin')],check=True,capture_output=True,text=True)
    (output/'encoder-reference.stdout').write_text(ts_result.stdout)
    (output/'encoder-reference.stderr').write_text(ts_result.stderr)
    # Compile-only RV32 check using the pinned local compiler; no firmware calls or device.
    cross = [str(args.rvcc),'-march=rv32imafc','-mabi=ilp32f','-mstrict-align','-mno-relax',
             '-std=c11','-Os','-ffreestanding','-fno-builtin','-fno-jump-tables',
             '-ffunction-sections','-fdata-sections','-fstack-usage','-Wall','-Wextra','-Werror',
             '-Wno-unused-function','-c',str(ROOT/'geometry.c'),'-o',str(output/'geometry-rv32.o')]
    crossed = subprocess.run(cross,capture_output=True,text=True)
    (output/'rv32-build.stderr').write_text(crossed.stderr)
    crossed.check_returncode()
    nm = str(args.rvcc).removesuffix('gcc') + 'nm'
    size = str(args.rvcc).removesuffix('gcc') + 'size'
    undefined = subprocess.check_output([nm,'-u',str(output/'geometry-rv32.o')],text=True)
    (output/'rv32-undefined.txt').write_text(undefined)
    if undefined.strip():
        raise RuntimeError('Unexpected RV32 external symbols: '+undefined)
    sizes = subprocess.check_output([size,'-A',str(output/'geometry-rv32.o')],text=True)
    (output/'rv32-sections.txt').write_text(sizes)
    rle_cross=cross.copy()
    rle_cross[rle_cross.index(str(ROOT/'geometry.c'))]=str(ROOT/'rle.c')
    rle_cross[-1]=str(output/'rle-rv32.o')
    built=subprocess.run(rle_cross,check=True,capture_output=True,text=True)
    (output/'rle-rv32-build.stderr').write_text(built.stderr)
    rle_undefined=subprocess.check_output([nm,'-u',str(output/'rle-rv32.o')],text=True)
    (output/'rle-rv32-undefined.txt').write_text(rle_undefined)
    if rle_undefined.strip():raise RuntimeError('Unexpected RLE external symbols: '+rle_undefined)
    (output/'rle-rv32-sections.txt').write_text(subprocess.check_output([size,'-A',str(output/'rle-rv32.o')],text=True))
    report={'source_commit' :revision,'source_hashes_verified':len(upstream['files']),
            'host_build':build,'rv32_compile':cross,'rle_host_build':rle_build, 'rle_rv32_compile':rle_cross,
            'rle_result':rle_result.stdout.strip(),'encoder_result':ts_result.stdout.strip(),'result':result.stdout.strip(),
            'tools':{'clang':subprocess.check_output([args.cc,'--version'],text=True).splitlines()[0],
                     'bun':subprocess.check_output(['bun','--version'],text=True).strip(),
                     'riscv_gcc':subprocess.check_output([str(args.rvcc),'--version'],text=True).splitlines()[0]},
            'portable_input_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(ROOT.rglob('*')) if p.is_file() and p.suffix in ('.c','.h','.py','.json')},
            'rv32_undefined_symbols':[],'hardware_tested':False,'output':str(output)}
    vector_result=subprocess.run([sys.executable,str(ROOT/'tests/run_vector_tests.py'),
        '--output',str(output/'vector'),'--g2-source',str(g2),'--cc',args.cc,'--rvcc',str(args.rvcc)],
        check=True,capture_output=True,text=True)
    (output/'vector-runner.stdout').write_text(vector_result.stdout)
    (output/'vector-runner.stderr').write_text(vector_result.stderr)
    report['vector_report']='vector/report.json'
    report['vector_result']=json.loads((output/'vector/report.json').read_text())['result']
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
