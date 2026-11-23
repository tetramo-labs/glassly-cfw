#!/usr/bin/env python3
"""Create hash/individual-assertion inventory and explicit MemoMind port mapping."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parent
SNAP=ROOT/'upstream'


def mask(text):
    return re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                  lambda m: ''.join('\n' if c=='\n' else ' ' for c in m[0]),text)


def balanced(text,start,opening,closing):
    m=mask(text);depth=0
    for i in range(start,len(text)):
        if m[i]==opening:depth+=1
        elif m[i]==closing:
            depth-=1
            if depth==0:return i+1
    raise ValueError('Unbalanced source')


def predicates(text,names=('CHECK','assert','expect')):
    m=mask(text);result=[]
    for match in re.finditer(r'\b('+ '|'.join(names)+r')\s*\(',m):
        line_start=text.rfind('\n',0,match.start())+1
        if text[line_start:match.start()].lstrip().startswith('#'):continue
        start=m.index('(',match.start());end=balanced(text,start,'(',')')
        expr=text[start+1:end-1]
        result.append({'line':text.count('\n',0,match.start())+1,'macro':match[1],
                       'expression':expr,'sha256':hashlib.sha256(expr.encode()).hexdigest()})
    return result


def function(text,name):
    m=mask(text);hit=re.search(r'^(?:static\s+)?[^\n;{}]+\b'+name+r'\s*\([^;{}]*\)\s*\{',m,re.M)
    if not hit:raise ValueError('Missing function '+name)
    start=m.index('{',hit.start());end=balanced(text,start,'{','}')
    return text[hit.start():end],text.count('\n',0,hit.start())+1,text.count('\n',0,end)+1


GROUPS={
 'ancs_relay_host_test.c':['test_left_lens_and_disabled','test_enable_status_and_source','test_attr_chunking','test_app_attr','test_ring_full_and_pacing','test_lease_expiry_and_epoch','test_send_failure','test_action','test_cleanup'],
 'keyboard_host_test.c':['isolation','commands','reports','prompts','malformed','timers'],
 'shapes_host_test.c':['test_immediate','test_easing','test_cache_basic','test_identity','test_lru','test_assets','test_offsets','test_transactions','test_hidden_animation','test_clock_tweens','test_state','test_lifecycle','test_asset_replacement','test_reassert','test_transaction_rollback','test_upload_continuation'],
 'transport_host_test.c':['subset_records','outside_records','compressed_records','skipped_reset_is_not_borrowed','handler_failure'],
 'upstream_host_test.c':['routing','batteries','settings','headings','ble_link'],
 'vector_host_test.c':['pixels_and_paths','rotations','invalid_and_lifecycle','fuzz'],
 'volume_gate_host_test.c':['main']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true',help='Fail if checked-in inventory differs; never write it')
    args=parser.parse_args()
    pin=json.loads((ROOT/'UPSTREAM.json').read_text())
    rows=[]
    for path in sorted((SNAP/'patches/host').glob('*')):
        name=str(path.relative_to(SNAP));text=path.read_text();base=path.name
        row={'upstream_file':name,'upstream_sha256':pin['copied_files'][name],
             'memo_copy':str(path.relative_to(ROOT.parent.parent)), 'assertions':predicates(text),
             'status':'unimplemented','scope':'MemoMind implementation not yet equivalent',
             'counterpart':None,'reference_execution':'not-run'}
        if base in GROUPS:
            row['test_count']=len(GROUPS[base]);row['test_count_basis']='distinct named scenario functions; loop iterations and inherited suites excluded'
            row['test_groups']=[]
            for group in GROUPS[base]:
                body,lo,hi=function(text,group)
                row['test_groups'].append({'name':group,'line':lo,'end_line':hi,'assertion_sites':len(predicates(body)),
                                           'status':'unimplemented','counterpart':None})
            row['reference_execution']='passed ASan+UBSan, analysis/g2-compat-tests-02/'
            row['dependencies']=['host C compiler','ASan','UBSan','copied pinned C sources']
            if base=='volume_gate_host_test.c':
                row['status']='ported';row['scope']='pure volume gate state machine only; MemoMind audio integration absent'
                row['counterpart']='tests/g2_compat/portable_algorithms/volume_gate_core.h'
                row['test_groups'][0].update(status='ported',counterpart=row['counterpart'])
            elif base=='shapes_host_test.c':
                row['scope']='partially ported: geometric test_immediate predicates and easing; retained scenes/assets unimplemented'
                ported=predicates((ROOT/'ported_shapes.c').read_text())
                preserved={p['expression'].replace('memo_immediate(', 'cfw_shapes_immediate(') for p in ported}
                geometric_lines={383,389,390,391,392,393,395,397,399,401,410,413,415,422}
                selected=[p for p in row['assertions'] if p['line'] in geometric_lines and p['expression'] in preserved]
                # Header CHECK macro must not count; exactly fourteen original sites are retained.
                if len(selected)!=14:raise RuntimeError('Geometric predicate identity changed')
                row['ported_assertion_sites']=[p['line'] for p in selected]
                row['test_groups'][0].update(status='unimplemented',ported_assertion_sites=14,
                    counterpart='tests/g2_compat/ported_shapes.c -> runtime/portable/geometry.c',
                    note='Original fixture geometry and14predicates preserved; unsupported asset/font sections remain unimplemented')
                row['test_groups'][1].update(status='ported',counterpart='tests/g2_compat/ported_easing.c +portable_algorithms/easing.h')
                row['related_ported_boundaries']=[{'counterpart':'runtime/portable/rle.c','test':'runtime/portable/tests/test_rle.c','source_fixture':'mk_image + test_assets original 24x24 malformed image mutation','scope':'RLE acceptance boundary only; original cache reply/asset lifetime predicate remains unimplemented'}]
            elif base=='vector_host_test.c':
                row['inherited_scenarios']={'file':'patches/host/shapes_host_test.c','count':16,'deduplicate':True}
                row['dependencies']+=['retained object/cache integration','timer/display/memory adapters']
                ported=predicates((ROOT.parent.parent/'runtime/portable/tests/test_vector.c').read_text(),('CHECK',))
                origin_lines=[37,37,38,42,45,49,58,59,59,71,72,72,106,166,175,98]
                if len(ported)!=len(origin_lines):raise RuntimeError('Vector predicate count changed')
                mapped=[]
                for assertion,line in zip(ported,origin_lines):
                    matches=[p for p in row['assertions'] if p['line']==line and p['expression']==assertion['expression']]
                    if len(matches)!=1:raise RuntimeError('Original vector predicate changed '+str(line))
                    mapped.append({'upstream_line':line,'expression':assertion['expression'],
                                   'sha256':assertion['sha256'],'ported_line':assertion['line']})
                row['ported_assertions']=mapped
                row['counterpart']='runtime/portable/vector.c + runtime/portable/tests/test_vector.c'
                row['scope']='16 original compiler/math/pixel predicates ported; scene/cache/lifecycle/timing predicates remain unimplemented'
                for group in row['test_groups']:
                    group['counterpart']=row['counterpart']
                    group['ported_assertion_sites']=sum(group['line']<=m['upstream_line']<=group['end_line'] for m in mapped)
                row['portable_execution']='20026 original predicate evaluations; 10063 compiler +483 raster comparisons; analysis/portable-vector-tests-05/'
            else:
                row['status']='platform-specific'
                row['scope']='G2 BLE/service/stock-import assertions preserved; MemoMind adapter not implemented'
                for group in row['test_groups']:group['status']='platform-specific'
                if base=='transport_host_test.c':
                    row['dependencies']+=['host zlib','MemoMind transport adapter preserving abstract record/CRC/reply cases']
                    row['related_non_equivalent_tests']=['scripts/test_memomind_transport.py','scripts/test_decode_memomind.py','scripts/test_memomind_flasher.py']
                elif base=='keyboard_host_test.c':row['dependencies']+=['generated keyboard_timer_functions.inc','MemoMind HOGP/queue/timer ABI']
                elif base=='upstream_host_test.c':row['dependencies']+=['generated upstream_functions.inc','MemoMind settings/sensors/link ownership']
                else:row['dependencies']+=['MemoMind notification relay/task/lifetime ABI']
            if base=='ancs_relay_host_test.c':
                counterpart='runtime/portable/tests/notifications/'+base
                port_asserts=predicates((ROOT.parent.parent/counterpart).read_text(),('CHECK',))
                source_asserts=predicates(text,('CHECK',))
                if [a['expression'] for a in source_asserts]!=[a['expression'] for a in port_asserts]:
                    raise RuntimeError('Notification predicate identity changed')
                row.update(scope='All nine original host scenarios exercise portable notification core; stock chaining, G2 ANCC layout and action-handle checks use test-only shim, so native coverage remains incomplete',
                    counterpart='runtime/portable/notifications.c + '+counterpart,
                    portable_core_status='ported',
                    portable_execution='76 unchanged CHECK sites /266 evaluations; ASan+UBSan plus separate public API tests and RV32 compile audit; analysis/portable-notification-tests-02/',
                    ported_assertions=[{'upstream_line':a['line'],'ported_line':b['line'],'expression':a['expression'],'sha256':a['sha256']} for a,b in zip(source_asserts,port_asserts)],
                    pending_platform_boundaries=['MemoMind notification discovery/source/attribute adapter','native action and connection validation','outbound transport envelope','native queue/timer/allocator ownership and scheduler testing'])
                row['dependencies']=['host Clang ASan/UBSan','portable production notification sources','explicit platform callbacks','test-only G2 ABI shim']
                for group in row['test_groups']:
                    group.update(counterpart=row['counterpart'],portable_core_status='exercised',
                        native_adapter_status='pending')
            if base=='keyboard_host_test.c':
                counterpart='runtime/portable/tests/keyboard/'+base
                port_asserts=predicates((ROOT.parent.parent/counterpart).read_text(),('assert',))
                source_asserts=predicates(text,('assert',))
                if [a['expression'] for a in source_asserts]!=[a['expression'] for a in port_asserts]:
                    raise RuntimeError('Keyboard predicate identity changed')
                row.update(scope='All six original host scenarios exercise portable keyboard core; G2 event structures and native callbacks use test-only adapter, so native coverage remains incomplete',
                    counterpart='runtime/portable/keyboard.c + '+counterpart,
                    portable_core_status='ported',
                    portable_execution='86 unchanged assert sites /966 evaluations; ASan+UBSan plus separate public API tests and RV32 compile audit; analysis/portable-keyboard-tests-02/',
                    ported_assertions=[{'upstream_line':a['line'],'ported_line':b['line'],'expression':a['expression'],'sha256':a['sha256']} for a,b in zip(source_asserts,port_asserts)],
                    pending_platform_boundaries=['MemoMind HOGP discovery/ATT/DM/security adapters','native lifecycle/timer/worker queue ownership','outbound transport envelope','eight G2 ARM machine scenarios require separate native RV32 equivalents'])
                row['dependencies']=['host Clang ASan/UBSan','portable production keyboard sources','explicit platform callbacks','test-only G2 ABI shim']
                for group in row['test_groups']:
                    group.update(counterpart=row['counterpart'],portable_core_status='exercised',
                        native_adapter_status='pending')
            if base=='transport_host_test.c':
                counterpart='runtime/portable/tests/transport/'+base
                port_asserts=predicates((ROOT.parent.parent/counterpart).read_text(),('assert',))
                source_asserts=predicates(text,('assert',))
                if [a['expression'] for a in source_asserts]!=[a['expression'] for a in port_asserts]:
                    raise RuntimeError('Transport predicate identity changed')
                row.update(scope='All five original scenarios exercise production portable record parser/CRC/state/replies; G2 outer frames, simulated two-lens routing and host zlib are explicit test adapters',
                    counterpart='runtime/portable/transport.c + '+counterpart,
                    portable_core_status='ported',
                    portable_execution='50 unchanged assert sites and original scenario bodies/fixtures; ASan+UBSan plus separate public API tests and RV32 compile audit; analysis/portable-transport-tests-02/',
                    ported_assertions=[{'upstream_line':a['line'],'ported_line':b['line'],'expression':a['expression'],'sha256':a['sha256']} for a,b in zip(source_asserts,port_asserts)],
                    pending_platform_boundaries=['native GM transport routing/ordering/backpressure/lifetime adapter','native RFC1950 inflater availability and binding','native record memory budget and handler context','logical destination mapping; MemoMind dual-lens topology not assumed'])
                row['dependencies']=['host Clang ASan/UBSan','host zlib','portable production record parser','test-only G2 outer-frame/topology shim']
                for group in row['test_groups']:
                    group.update(counterpart=row['counterpart'],portable_core_status='exercised',
                        native_adapter_status='pending')
            if base=='upstream_host_test.c':
                counterpart='runtime/portable/tests/upstream/'+base
                port_asserts=predicates((ROOT.parent.parent/counterpart).read_text(),('assert',))
                source_asserts=predicates(text,('assert',))
                if [a['expression'] for a in source_asserts]!=[a['expression'] for a in port_asserts]:
                    raise RuntimeError('Upstream policy predicate identity changed')
                row.update(scope='All five original scenarios exercise portable extension parsing, settings composition, battery encoding, heading and link policies; G2 native layouts/hooks are test-only adapters',
                    counterpart='runtime/portable/upstream.c + '+counterpart,
                    portable_core_status='ported',
                    portable_execution='78 unchanged assert sites /25620 evaluations and unchanged scenario bodies; ASan+UBSan plus separate public API tests and RV32 compile audit; analysis/portable-upstream-tests-01/',
                    ported_assertions=[{'upstream_line':a['line'],'ported_line':b['line'],'expression':a['expression'],'sha256':a['sha256']} for a,b in zip(source_asserts,port_asserts)],
                    pending_platform_boundaries=['MemoMind extension control routing and settings response composition','native timestamped compass/raw IMU sensor adapters','native BLE connection policy/lifecycle mapping; no RFCOMM acceleration claim','G2 stock hook passthrough and memory-layout assertions are test-only'])
                row['dependencies']=['host Clang ASan/UBSan','portable production protocol/policy sources','explicit typed inputs/callbacks','test-only G2 native-layout shim']
                for group in row['test_groups']:
                    group.update(counterpart=row['counterpart'],portable_core_status='exercised',
                        native_adapter_status='pending')
            if base in ('shapes_host_test.c','vector_host_test.c'):
                full_port=ROOT.parent.parent/'runtime/portable/tests/scene'/base
                port_asserts=predicates(full_port.read_text(),('CHECK',))
                source_asserts=predicates(text,('CHECK',))
                if [a['expression'] for a in source_asserts]!=[a['expression'] for a in port_asserts]:
                    raise RuntimeError('Full scene predicate identity changed: '+base)
                row.update(status='ported',scope='Complete original host suite uses production portable scene/cache/assets and geometry/vector; native built-in font remains explicit callback with unchanged upstream box stub',
                    counterpart='runtime/portable/scene.c + runtime/portable/tests/scene/'+base,
                    portable_execution='ASan+UBSan passed; combined42466 original CHECK evaluations, zero failures/leaks; analysis/portable-scene-tests-03/',
                    ported_assertions=[{'upstream_line':a['line'],'ported_line':b['line'],'expression':a['expression'],'sha256':a['sha256']} for a,b in zip(source_asserts,port_asserts)],
                    pending_platform_boundaries=['native built-in font callback','native allocator/timer/display integration and device memory budget'])
                row.pop('ported_assertion_sites',None)
                row['dependencies']=['host Clang ASan/UBSan','portable production scene/geometry/vector sources','explicit host platform callbacks']
                for group in row['test_groups']:
                    group.update(status='ported',counterpart=row['counterpart'])
                    group.pop('note',None);group.pop('ported_assertion_sites',None)
        elif base=='keyboard_emulator_test.py':
            tree=ast.parse(text);row['assertions']=[{'line':n.lineno,'expression':ast.get_source_segment(text,n.test)} for n in ast.walk(tree) if isinstance(n,ast.Assert)]
            names=['dormant','pairing_and_routing','io_capability','att_requests','fragments_overflow_and_oom','timeout_and_disable','scan_and_capacity','allocation_failure']
            row.update(status='platform-specific',test_count=8,test_count_basis='explicit main scenario list',test_groups=names,
                dependencies=['g2emu commit f30527c0b7e6fa6e9be06e7067e49468197fa258','Unicorn ARM','matching G2 firmware and compiled build symbols','five ARM hook-site witnesses','new RV32 equivalent absent'])
            row['related_non_equivalent_tests']=['tests/rv32/probe_emulator_test.py']
            row['related_scope']='Actual MemoMind RV32 probe execution tests exist, but do not cover the eight G2 keyboard scenarios'
        elif base=='run_vector_tests.py':
            row.update(test_count=0,test_count_basis='orchestrator, not an additional independent test',
                counterpart='tests/g2_compat/run_tests.py',scope='offline host/TypeScript/fixture/video orchestration and MemoMind scene/path replays ported; notification/settings/transport adapters and full RV32 runtime incomplete; keyboard reference optional',
                dependencies=['Bun','TypeScript','g2-kit/protobuf','host cc/zlib','GIF and prepared SVG video fixtures','G2 Thumb builder; replace for MemoMind'])
            row['stages']=['5 host support suites','vector suite includes shapes','3 Bun test files','2 tsc configs','TS vector fixture dump/replay','Bad Apple GIF300-frame replay','optional prepared YouTube SVG replay','Thumb build relocation check']
            row['reference_execution']='Host, Bun, both tsc configs, generated24-message vector fixture and both300-frame media replays passed in analysis/regression-20261031-01/g2_compat/report.json; these replay G2 reference code'
            row['memo_replacement_build_tests']=['scripts/compile_memomind_probe.py','tests/rv32/probe_emulator_test.py',
                'scripts/compile_memomind_graphics.py','tests/rv32/graphics_gate_emulator_test.py',
                'tests/rv32/graphics_runtime_emulator_test.py','tests/rv32/scene_runtime_emulator_test.py',
                'tests/rv32/input_gate_emulator_test.py','tests/rv32/input_runtime_emulator_test.py']
            row['replacement_build_scope']='Actual RV32 probe, graphics, retained scenes and input observer with explicit native mocks; full notification/transport/policy bindings remain pending; keyboard bindings excluded from required parity'
            row['aggregate_counterpart']='tests/run_tests.py'
            row['aggregate_stage_mapping']={
                '5 host support suites (4 required; keyboard optional)':['g2_compat','notifications','record_transport','upstream_policy'],
                'vector suite includes shapes':['g2_compat','geometry','scene','scene_session_host'],
                '3 Bun test files (2 required; keyboard optional)':['g2_compat'], '2 tsc configs (vector required; keyboard optional)':['g2_compat'],
                'TS vector fixture dump/replay':['g2_compat','scene','scene_session_host'],
                'Bad Apple GIF300-frame replay':['g2_compat','scene','scene_session_host'],
                'optional prepared YouTube SVG replay':['g2_compat','scene','scene_session_host'],
                'Thumb build relocation check':['rv32_build','rv32_probe','graphics_build','graphics_gates',
                    'graphics_runtime','scene_build','scene_gates','scene_runtime','input_build','input_gates','input_runtime']}
        else:
            row.update(status='ported',test_count=0,test_count_basis='stdin path compiler validation harness, not a named test suite',
                       counterpart='runtime/portable/tests/vector_path_check.c',
                       scope='original stdin/read/count/exit behavior reproduced with portable compiler; 291 exact reference comparisons',
                       reference_execution='passed ASan+UBSan, analysis/portable-vector-tests-05/',
                       dependencies=['host C compiler','ASan/UBSan','pinned original source'])
        row['assertion_site_count']=len(row['assertions']);rows.append(row)
    for path in sorted((SNAP/'demos').glob('*.test.ts')):
        name=str(path.relative_to(SNAP));text=path.read_text()
        cases=[]
        for hit in re.finditer(r'\btest\(\s*(["\'])(.*?)\1',text):
            label=hit[2];specific=('settings read' in label or 'dedicated field' in label)
            cases.append({'name':label,'line':text.count('\n',0,hit.start())+1,
                          'status':'platform-specific' if specific else 'ported',
                          'scope':'G2 outer settings wire case' if specific else 'phone-side pure algorithm/codec test; device integration unimplemented'})
        rows.append({'upstream_file':name,'upstream_sha256':pin['copied_files'][name],
                     'memo_copy':str(path.relative_to(ROOT.parent.parent)),'test_count':len(cases),'test_count_basis':'named Bun test() declarations',
                     'test_groups':cases,'assertion_site_count':len(predicates(text,('expect',))),
                     'assertions':predicates(text,('expect',)),
                     'status':'platform-specific' if any(c['status']=='platform-specific' for c in cases) else 'ported',
                     'scope':'complete unchanged source tests executed locally; G2 outer wire selectors not MemoMind routing',
                     'counterpart':str(path.relative_to(ROOT.parent.parent)),
                     'dependencies':['Bun','copied installed g2-kit e8530502419bed4f5fb02c370c522208117c01d2 dependency tree','@bufbuild/protobuf'],
                     'reference_execution':'21 tests /5770 expect evaluations passed across three files; analysis/g2-compat-tests-02/typescript.stderr'})
    for name in ['send_message_probe.py','demos/bad-apple-tests.ts','demos/cache-probe.ts','demos/head-up-test.ts','demos/ring-touch-test.ts','demos/sound-test.ts','demos/video-test.sh','build_cfw.sh','demos/vector-suite.ts','demos/shapes-suite.ts',
                 'demos/video-bench.ts','demos/prepare-bad-apple.ts','demos/card-demo.ts',
                 'demos/shapes-demo.ts','demos/detect-cfw.ts','demos/keyboard.ts','demos/ble-mode.ts']:
        path=SNAP/name;text=path.read_text()
        rows.append({'upstream_file':name,'upstream_sha256':pin['copied_files'][name],'memo_copy':str(path.relative_to(ROOT.parent.parent)),
                     'test_count':None,'test_count_basis':'interactive/live demo or build integration; no unit-test registration',
                     'assertion_site_count':len(predicates(text)), 'status':'platform-specific',
                     'counterpart':None,'scope':'G2 device/build harness; not executed',
                     'dependencies':['real G2 BLE/device and matching firmware/features; or G2 image/build environment'],
                     'reference_execution':'not-run; never counted as pass'})
        if name in ('demos/vector-suite.ts','demos/prepare-bad-apple.ts'):
            rows[-1]['status']='unimplemented'
            rows[-1]['scope']='offline asset/fixture generation pipeline preserved; MemoMind scene/session replay implemented; live transport and native integration verification remain incomplete'
            rows[-1]['dependencies']=['Bun/dependency tree','GIF or prepared SVG video corpus','ffmpeg/Potrace for preparation','Native MemoMind live scene/device verification']
    # Preserve every original row/predicate and its technical port status. Scope is
    # independent: keyboard/HOGP accessory support was explicitly excluded by the
    # user on 2026-11-01. Mixed settings/routing tests remain required unchanged.
    keyboard_files={'patches/host/keyboard_host_test.c',
                    'patches/host/keyboard_emulator_test.py',
                    'demos/keyboard.test.ts','demos/keyboard.ts'}
    gesture_files={'demos/head-up-test.ts','demos/ring-touch-test.ts'}
    sound_files={'demos/sound-test.ts'}
    volume_files={'patches/host/volume_gate_host_test.c'}
    excluded_files=keyboard_files|gesture_files|sound_files|volume_files
    for row in rows:
        excluded=row['upstream_file'] in excluded_files
        row['parity_required']=not excluded
        row['parity_scope']=('optional-keyboard-reference' if row['upstream_file'] in keyboard_files else 'optional-volume-gate-reference' if row['upstream_file'] in volume_files else 'optional-sound-reference' if row['upstream_file'] in sound_files else 'optional-gesture-reference') if excluded else 'required'
        if excluded:
            row['exclusion_reason']=('User excluded Bluetooth keyboard/HOGP on 2026-11-01' if row['upstream_file'] in keyboard_files else 'User excluded volume gating on 2026-11-02; microphone capture and streaming remain in scope' if row['upstream_file'] in volume_files else 'User excluded mode5 sound/tone commands on 2026-11-02; microphone remains in scope' if row['upstream_file'] in sound_files else 'User excluded gestures on 2026-11-02: hardware has one button; head-up and ring-touch acceptance are not required')+'; historical sources/tests retained, not counted as completed parity'
        for group in row.get('test_groups',[]):
            if isinstance(group,dict):group['parity_required']=not excluded
        if row['upstream_file']=='patches/host/upstream_host_test.c':
            row['scope_note']='Mixed routing/settings/compass/link scenarios remain required. Original source and reference runs retain battery/keyboard structural checks, but do not require native ring battery reports or keyboard hardware. Native settings expectations must distinguish unsupported selectors. Compass/raw IMU data remain in scope.'
            for group in row['test_groups']:
                if group['name']=='batteries':
                    group['parity_required']=False
                    group['parity_scope']='optional-ring-battery-reference'
                    group['exclusion_reason']='User excluded ring battery on 2026-11-02; no ring battery hardware'
            row['required_test_count']=sum(g['parity_required'] for g in row['test_groups'])
            row['required_assertion_site_count']=row['assertion_site_count']-sum(g['assertion_sites'] for g in row['test_groups'] if not g['parity_required'])
        if row['upstream_file']=='patches/host/run_vector_tests.py':
            row['optional_reference_stage_mapping']={'keyboard host/TypeScript reference':['keyboard','g2_compat --include-keyboard-reference']}
    required_host=[r for r in rows if Path(r['upstream_file']).name in GROUPS and r['parity_required']]
    report={'upstream_commit':pin['commit'],'inventory_scope':'all tracked patches/host C/Python files, demos *.test.ts, tracked test/probe/build harnesses',
            'parity_scope':{'effective_date':'2026-11-02','excluded_features':['Bluetooth keyboard/HOGP accessory support','Ring battery','Gesture recognition and gesture-triggered controls (including head-up and ring-touch)','Mode5 sound and tone commands','Microphone volume gating'],
                'required_hardware_features':['Single-button input','Compass data','Raw IMU data','Ambient-light sensing'],
                'excluded_upstream_files':sorted(excluded_files),'historical_tests_retained':True,
                'mixed_non_keyboard_suites_remain_required':True,'command_parity_map':'tests/g2_compat/COMMAND_PARITY.md'},
            'required_host_core_scenarios':{'total':sum(r.get('required_test_count',r['test_count']) for r in required_host),
                'original_assertion_sites':sum(r.get('required_assertion_site_count',r['assertion_site_count']) for r in required_host),
                'native_adapter_coverage_included':False},
            'required_bun_test_cases':sum(r['test_count'] for r in rows if r['upstream_file'].endswith('.test.ts') and r['parity_required']),
            'counting_rules':'test_count counts named scenarios, not CHECK/assert/expect sites or repeated evaluations. Inherited shape scenarios in vector are not added twice. Mixed suites remain unimplemented/platform-specific at file level.',
            'host_core_scenarios':{'total':sum(len(v) for v in GROUPS.values()),
                'exercised':sum(1 for row in rows if Path(row['upstream_file']).name in GROUPS
                    for group in row['test_groups'] if group['status']=='ported' or group.get('portable_core_status')=='exercised'),
                'original_assertion_sites':sum(r['assertion_site_count'] for r in rows if Path(r['upstream_file']).name in GROUPS),
                'native_adapter_coverage_included':False},
            'rows':rows,'g2flash_python_unit_suite':{'found':False,'searched':'tracked g2flash repository test/spec/check/probe paths and all patches/host files',
                'note':'g2flash.py is a device CLI with validation assertions, not a discovered unittest/pytest suite; no test coverage is inferred from those assertions',
                'memo_counterparts':['scripts/test_memomind_flasher.py','scripts/test_memomind_ota.py','scripts/test_decode_memomind.py'],'equivalent':False},
            'portable_algorithm_boundaries':[
                {'upstream_file':name,'upstream_sha256':pin['copied_files'][name],
                 'upstream_functions':functions,'status':'ported','counterpart':counterpart,
                 'tests':('runtime/portable/tests/run_scene_tests.py' if 'scene' in counterpart else ('runtime/portable/tests/run_vector_tests.py' if name=='patches/vector.c' else 'runtime/portable/tests/run_tests.py')),
                 'evidence':('analysis/portable-scene-tests-03/' if 'scene' in counterpart else ('analysis/portable-vector-tests-05/' if name=='patches/vector.c' else 'analysis/portable-geometry-rle-tests-02/')),
                 'scope':scope}
                for name,functions,counterpart,scope in [
                    ('patches/rle.c',['rle_init','rle_emit','rle_feed'],'runtime/portable/rle.c',
                     'bounded packed-nibble stream decode; byte stores replace word stores, complete prevalidation before writes'),
                    ('patches/texture_cache.c',['cfw_texture_rle_token'],'runtime/portable/rle.c',
                     'token parser only; no cached image/font rendering or asset lifetime integration'),
                    ('demos/video-bench.ts',['rleEncode'],'runtime/portable/rle.c',
                     'canonical bounded encoder; 378 cases byte-identical to unchanged extracted TypeScript encoder'),
                    ('patches/vector.c',['cv_compile','cv_curve','cv_fill','cv_path_draw','cv_shape_draw','cv_transform'],'runtime/portable/vector.c',
                     'caller-owned workspace/path/raster; scene integration uses this implementation'),
                    ('patches/scene.c',['cfw_scene_dispatch','cfw_cache_prepare','scene_tick','cfw_txn_abort','cfw_txn_commit'],'runtime/portable/scene.c + scene_cache.inc',
                     'full modes37..41 cache/transaction/lifecycle/tween/state core; explicit platform callbacks, no device hooks'),
                    ('patches/texture_cache.c',['cfw_texture_image_in','cfw_texture_font_valid','cfw_texture_draw_image_region','cfw_texture_draw_string_region','cfw_texture_string_valid'],'runtime/portable/scene_assets.inc',
                     'cached image/font/UTF8 validation and rendering; built-in native font excluded behind callback')]],
            'native_command_regressions':[
                {'modes':[7,11], 'upstream_file':'patches/zlib_glue.c',
                 'upstream_sha256':pin['copied_files']['patches/zlib_glue.c'],
                 'upstream_functions':['image_dispatch'],
                 'tracking_reference':{'upstream_file':'patches/debug.c',
                    'upstream_sha256':pin['copied_files']['patches/debug.c'],
                    'upstream_functions':['cfw_diag']},
                 'counterpart':'runtime/graphics/diagnostics.c + graphics.c + input.c (MM_DIAGNOSTIC_COMMANDS)',
                 'test':'runtime/graphics/tests/run_diagnostic_command_tests.py',
                 'aggregate_stages':['diagnostic_command_host','diagnostic_command_build','diagnostic_command_runtime',
                    'diagnostic_command_gates','diagnostic_command_canary','diagnostic_command_reader',
                    'diagnostic_command_input','diagnostic_command_scene','diagnostic_command_bundle',
                    'diagnostic_command_text','diagnostic_command_canary_contract','diagnostic_command_reader_contract'],
                 'scope':'Original G2 frame/control differentials and compiled native adapters with firmware/LVGL mocks. Cleanup covers implemented graphics/input only; current-screen history and best-effort explicit-cleanup epoch retention. Native counters/overlay differ from G2. No native sensor, full-controller cleanup or hardware equivalence inferred.',
                 'counted_as_original_suite_completion':False},
                {'modes':[15], 'upstream_file':'patches/texture_cache.c',
                 'upstream_sha256':pin['copied_files']['patches/texture_cache.c'],
                 'upstream_functions':['cfw_builtin_draw_string_buf','cfw_builtin_draw_string'],
                 'counterpart':'runtime/graphics/native_text.c + scene_session.c (MM_TEXT_COMMANDS)',
                 'test':'runtime/graphics/tests/run_text_command_tests.py',
                 'aggregate_stages':['text_command_host','text_command_build','text_command_runtime',
                    'text_command_gates','text_command_canary','text_command_reader','text_command_input',
                    'text_command_scene','text_command_bundle','text_command_canary_contract','text_command_reader_contract'],
                 'scope':'Original G2 text functions with equivalent synthetic glyphs; Memo native queue/RV32 adapters with explicit font and firmware mocks. Native font repertoire, metrics and missing-glyph behavior differ; no full font or hardware equivalence inferred.',
                 'counted_as_original_suite_completion':False}],
            'full_memo_suite_port_complete':False,'unimplemented_or_platform_specific_are_passes':False}
    if args.check:
        if json.loads((ROOT/'inventory.json').read_text())!=report:
            raise RuntimeError('Stale assertion inventory; regenerate with tests/g2_compat/inventory.py')
    else:
        (ROOT/'inventory.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'inventory_files':len(rows),'host_unique_scenario_groups':sum(len(v) for v in GROUPS.values()),
                      'bun_test_cases':sum(r['test_count'] for r in rows if r['upstream_file'].endswith('.test.ts')),
                      'required_host_scenarios':report['required_host_core_scenarios']['total'],
                      'required_bun_test_cases':report['required_bun_test_cases'],'complete':False}))


if __name__=='__main__':main()
