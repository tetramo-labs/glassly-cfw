#!/usr/bin/env python3
"""Read-only dry-run of just admission's catalog/test transforms using memory IO.
Synthetic pins are NOT firmware evidence and generated text is never installed.
"""
from pathlib import Path
import ast, collections, hashlib, json, re, sys
if not __debug__: raise RuntimeError('Assertions required')
ROOT=Path(__file__).resolve().parents[3]; OUT=Path(sys.argv[1]); OUT.mkdir(exist_ok=False)
p=ROOT/'analysis/text-native-20261102/admit-candidate.py'; source=p.read_text(); ast.parse(source)
files={name:(ROOT/name).read_text() for name in ['swift/MemoMindKit/Sources/MemoMindCore/FirmwareImage.swift','swift/MemoMindKit/Tests/MemoMindCoreTests/FirmwareImageTests.swift']}
written={}
class MemoryPath:
 def __init__(self,name): self.name=name; assert name in files
 def read_text(self): return files[self.name]
 def write_text(self,s): written[self.name]=s
start=source.index("p=Path('swift/MemoMindKit/Sources/MemoMindCore/FirmwareImage.swift')")
end=source.index('for template in root.glob',start)
transform=source[start:end]
pins=dict(image_sha256='a'*64,header_sha256='b'*64,metadata_sha256='c'*64,app_sha256='d'*64,app_packed_bytes=959111,app_raw_bytes=1838000)
ns=dict(Path=MemoryPath,pins=pins,image=bytes(2230111),blob=bytes(64784),streams=[dict(packed=bytes(171))])
exec(compile(transform,str(p)+'[transform-only]','exec'),ns)
oldcatalog,oldtests=files.values(); catalog,tests=written.values()
name_pattern=r'^    func (\w+)\('
oldnames=re.findall(name_pattern,oldtests,re.M); newnames=re.findall(name_pattern,tests,re.M)
counts=collections.Counter(newnames)
old_entries=re.findall(r'        FirmwareRelease\(name: "([^"]+)".*?streams: streamPins\(\.\w+\)\),',oldcatalog,re.S)
entry_matches=list(re.finditer(r'        FirmwareRelease\(name: "([^"]+)".*?streams: streamPins\(\.\w+\)\),',oldcatalog,re.S))
checks=dict(all_old_catalog_entries_unchanged=all(m.group() in catalog for m in entry_matches),all_old_test_names_present=all(n in newnames for n in oldnames),old_test_functions_preserved=True,text_catalog_entry_once=catalog.count('name: "text-commands-001"')==1,text_variant_once=catalog.count('case .text:')==1,text_enum_once=catalog.count('case stock, reader, canary, raster, rectCopy, bundle, text }')==1,text_digest_once=tests.count('private let textSHA = "'+'a'*64+'"')==1,new_text_test_methods_once=all(counts[n]==1 for n in ['testRequiredActualReviewedOfflineTextFixture','testTextEligibilityRejectsRepairedCRCsAndRawRuntime']))
# Every original top-level test declaration through the next declaration must
# remain verbatim (ignore boundary whitespace). No renamed-copy counts as old.
starts=list(re.finditer(name_pattern,oldtests,re.M))
for i,m in enumerate(starts):
 end=starts[i+1].start() if i+1<len(starts) else oldtests.rfind('\n}')
 if oldtests[m.start():end].strip() not in tests: checks['old_test_functions_preserved']=False
# Reverse only the three intended catalog additions; all previous pins, code,
# stream variants and order must recover byte-for-byte.
restored = re.sub(r'        // Exact reconstructed mode15 release; admission alone is not boot proof.\n        FirmwareRelease\(name: "text-commands-001".*?streams: streamPins\(\.text\)\),\n', '', catalog, flags=re.S)
restored=restored.replace('case stock, reader, canary, raster, rectCopy, bundle, text }','case stock, reader, canary, raster, rectCopy, bundle }')
restored=re.sub(r'        case \.text:.*?(?=        }\n        let sizes:)', '', restored, flags=re.S)
checks['entire_prior_catalog_code_and_pins_preserved']=restored==oldcatalog
newblocks=[]
for name in ['testRequiredActualReviewedOfflineTextFixture','testTextEligibilityRejectsRepairedCRCsAndRawRuntime']:
 m=re.search(r'^    func '+name+r'\(.*?(?=^    func |^})',tests,re.M|re.S); assert m
 newblocks.append(m.group())
checks['new_text_tests_have_no_stale_raster_or_bundle_pins']=all(not any(old in block for old in ['rasterSHA','bundleSHA','raster-commands-001','bundle-commands-001','2_227_971','61392','956_869','1_834_608']) for block in newblocks)
restoredtests=tests
for block in newblocks:restoredtests=restoredtests.replace(block,'',1)
restoredtests=restoredtests.replace('    private let textSHA = "'+'a'*64+'"\n\n','',1)
checks['entire_prior_test_source_preserved']=restoredtests==oldtests
report=dict(script_sha256=hashlib.sha256(source.encode()).hexdigest(),source_sha256={k:hashlib.sha256(v.encode()).hexdigest() for k,v in files.items()},synthetic_only=True,actual_admission_executed=False,checks=checks,old_releases=old_entries,old_test_method_count=len(oldnames),new_test_method_count=len(newnames),duplicates={n:c for n,c in counts.items() if c>1},added_names=[n for n in newnames if n not in oldnames])
report['pass']=all(checks.values()) and not report['duplicates'] and len(newnames)==len(oldnames)+2
(OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');(OUT/'transform.py.txt').write_text(transform)
(OUT/'generated-catalog.swift.txt').write_text(catalog);(OUT/'generated-tests.swift.txt').write_text(tests)
print(json.dumps(report,indent=2))
