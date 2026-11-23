#!/usr/bin/env python3
"""Linked ANCS C handlers and pre-stock wrapper, with stock APIs mocked."""
import argparse,json,struct,unittest
from pathlib import Path
import graphics_runtime_emulator_test as G
from flash_canary_runtime_emulator_test import CanaryMachine,REGISTRY

G.NATIVES.update({0x04319792:'stock_ancs',0x042361b8:'app_post',
                  0x042113ce:'ancs_peer',0x04318ee6:'ancs_action'})

class NotificationMachine(CanaryMachine):
    def __init__(self):
        super().__init__()
        self.stock_events=[];self.jobs=[];self.actions=[]
        self.peer=self.allocate(16,'native-peer')
        self.expected_event=None
    def region(self,address,size,writing=False):
        if REGISTRY+128<=address and address+size<=REGISTRY+140:
            assert self.critical
            return 'notification-registry'
        return super().region(address,size,writing)
    def native(self,name,args):
        a0,a1,a2,a3=args[:4]
        if name=='now':return self.now
        if name=='stock_ancs':
            assert not self.critical and tuple(args[:3])==self.expected_event
            self.stock_events.append(tuple(args[:3]));return 0
        if name=='app_post':
            assert not self.critical and (a0,a1,a3)==(0,0x280,8)
            self.jobs.append(self.read(a2,a3));return 0
        if name=='ancs_peer':
            assert not self.critical and self.read(a0,6)==bytes(range(1,7))
            return self.peer
        if name=='ancs_action':
            assert not self.critical
            self.actions.append((self.read(a0,6),self.word(a1),a2));return 0
        return super().native(name,args)
    def command(self,op,uid=42,action=0):
        data=b'AN\1'+bytes([op])+(struct.pack('<IB',uid,action) if op==4 else b'')
        reply,_=self.service(0x78,self.request(data))
        assert not self.critical
        return reply
    def observe(self,event,data):
        pointer=self.allocate(max(1,len(data)),'borrowed-ancs',data or bytes(1),writable=False)
        self.expected_event=(event,pointer,len(data))
        self.call('glassly_notification_entry',event,pointer,len(data))
        assert not self.critical and self.allocations[pointer]['live']
        self.discard(pointer)
    def source(self,flags=24,uid=42):
        self.observe(0x25a,bytes(range(1,7))+bytes([0,flags,1,1])+struct.pack('<I',uid))
    def attributes(self,body):
        pointer=self.allocate(len(body),'borrowed-body',body,writable=False)
        self.observe(0x25b,bytes(range(1,7))+bytes(2)+struct.pack('<IH2x',pointer,len(body)))
        self.discard(pointer)

class Tests(unittest.TestCase):
    def test_delivery_nested_body_and_session_reset(self):
        m=NotificationMachine();assert m.command(1)['active']==1
        m.source();first=m.command(0)
        assert '414e0101001801012a000000' in first['records']
        m.attributes(struct.pack('<IBH',42,1,3)+b'abc')
        assert any('616263' in record for record in m.command(0)['records'])
        m.source();m.observe(0x258,bytes(range(1,7))+bytes(6))
        reply=m.command(0)
        assert reply['session']!=first['session'] and not reply['connected']
        assert not any(record.startswith('414e0101') for record in reply['records'])
        m.source();assert m.command(0)['connected']==1
    def test_actions_busy_stale_and_lease(self):
        m=NotificationMachine();m.command(1);m.source(flags=8)
        assert m.command(4,action=1)['actionResult']==4
        assert m.command(4)['actionResult']==1
        m.observe(0x280,m.jobs.pop(0));assert m.command(0)['actionResult']==2
        assert m.actions==[(bytes(range(1,7)),42,0)]
        m.command(4);m.observe(0x280,m.jobs.pop(0));assert m.command(0)['actionResult']==3
        m.native_write(m.peer+12,bytes(1));m.command(4)
        m.source(uid=43);m.observe(0x280,m.jobs.pop(0));assert m.command(0)['actionResult']==4
        m.now+=90001;m.source();assert m.command(0)['active']==0
        m.command(1);m.source();m.call('glassly_notification_cleanup')
        assert m.command(0)['active']==0
        assert len(m.owned_live())==1  # Boot-owned relay only.
    def test_bounds_and_allocation_failure(self):
        m=NotificationMachine();m.command(1);m.source()
        m.attributes(struct.pack('<IBH',42,1,7)+b'abc')
        assert m.command(0)['rejected']==1
        m.observe(0x25b,bytes(range(1,7))+bytes(2)+struct.pack('<IH2x',0x020fedbf,8))
        assert m.command(2)['active']==0
        m=NotificationMachine();m.free_bytes=1024
        assert m.command(1)['result']=='unavailable' and not m.owned_live()

def main():
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    G.BUILD=a.build.resolve();G.PINNED_SHA=json.loads((G.BUILD/'build.json').read_text())['blob_sha256']
    result=unittest.TextTestRunner(verbosity=2,failfast=True).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    a.report.write_text(json.dumps({'passed':result.wasSuccessful(),'groups':result.testsRun,
        'runtimeSHA256':G.PINNED_SHA,'hardwareTested':False,'stockAPIsMocked':True,
        'maxObservedStackBytes':max((v['observed_stack_bytes'] for v in G.RESULTS),default=0),
        'calls':G.RESULTS},indent=2)+'\n')
    return not result.wasSuccessful()
if __name__=='__main__':raise SystemExit(main())
