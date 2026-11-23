import json,subprocess,time,sys
from pathlib import Path
out=Path('analysis/command-flags-20261103');began=time.monotonic();attempts=[];stage=sys.argv[1] if len(sys.argv)>1 else 'before'
while time.monotonic()-began<660:
    n=len(attempts)+1;capture=f'captures/command-flags-20261103-{stage}-{n:02d}'
    with (out/f'{stage}-search-{n:02d}.log').open('x') as log:
        r=subprocess.run([str(out/'hardware'),stage,capture],stdout=log,stderr=log)
    attempts.append(dict(capture=capture,exitCode=r.returncode,elapsedSeconds=time.monotonic()-began))
    (out/f'{stage}-search-result.json').write_text(json.dumps(dict(found=r.returncode==0,elapsedSeconds=time.monotonic()-began,attempts=attempts),indent=2)+'\n')
    if r.returncode==0 or (Path(capture)/"boot-checkpoint.json").exists():break
    time.sleep(10)
