#!/usr/bin/env python3
"""Conservative known-C frame sums; indirect callback costs remain unresolved."""
import json,re
from pathlib import Path
HERE=Path(__file__).resolve().parent
reports=[]
for mode in ('O2','Os'):
    frames,labels,edges={},{},{}
    for path in (HERE/mode).glob('*.ci'):
        text=path.read_text()
        for m in re.finditer(r'node: \{ title: "([^"]+)" label: "([^"]+)"',text):
            node,label=m.groups();labels[node]=label.split('\\n')[0]
            f=re.search(r'\\n(\d+) bytes \(static\)',label)
            if f:frames[node]=int(f[1])
        for m in re.finditer(r'edge: \{ sourcename: "([^"]+)" targetname: "([^"]+)"',text):
            edges.setdefault(m[1],set()).add(m[2])
    cycles=set()
    def path(node,counts):
        count=counts.get(node,0)
        limit=9 if labels.get(node)=='cv_curve' else 2 if labels.get(node)=='cfw_cache_prepare' else 1
        if count>=limit:
            if limit==1:cycles.add(labels.get(node,node))
            return None
        state=dict(counts);state[node]=count+1
        best=(0,[]);unknown=set()
        for target in edges.get(node,()):
            if target not in frames:
                unknown.add(target);continue
            child=path(target,state)
            if child is not None and child[0]>best[0]:best=child
        return (frames.get(node,0)+best[0],[{'name':labels.get(node,node),'frame':frames.get(node,0)}]+best[1])
    roots=[]
    for node in frames:
        if labels.get(node,'').startswith(('mm_scene_','mm_vector_','glassly_')):
            value=path(node,{})
            roots.append({'entry':labels[node],'known_C_frame_sum':value[0],'maximum_known_path':value[1]})
    unknown=sorted({t for ee in edges.values() for t in ee if t not in frames})
    reports.append({'optimization':mode,'method':'GCC -fcallgraph-info=su and .su; sums every direct parent frame (including tail-call candidates); cv_curve at most9 frames from depth0..8 guard; cfw_cache_prepare at most2 frames because mode8 only recurses into modes37..41',
                    'indirect_or_missing_boundaries':unknown,'other_cycles_detected':sorted(cycles),
                    'not_a_full_task_stack_bound':True,'roots':sorted(roots,key=lambda x:-x['known_C_frame_sum'])})
(HERE/'stack-graph.json').write_text(json.dumps(reports,indent=2)+'\n')
for report in reports:
    print(report['optimization'],'unknown',report['indirect_or_missing_boundaries'],'cycles',report['other_cycles_detected'])
    for root in report['roots'][:8]:print(root['entry'],root['known_C_frame_sum'],' -> '.join(x['name'] for x in root['maximum_known_path']))
