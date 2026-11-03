#!/usr/bin/env python3
"""Actual linked RV32 launcher/graphics/scene/COW; external kernel/I/O mocked.

The flash broker is covered separately with real pthread blocking queues and
native flash adapter. Here its bind seam installs explicit bounded physical I/O
callbacks, letting the display lifetime and 65535-byte carrier execute in RV32.
"""
import argparse,hashlib,json,struct,unittest,zlib
from pathlib import Path
import graphics_runtime_emulator_test as G
import scene_runtime_emulator_test as S
from diagnostic_command_runtime_emulator_test import DiagnosticMachine
G.NATIVES.update({0x05003000:'store_read',0x05003010:'store_erase',0x05003020:'store_program',0x04274b12:'welcome_home',0x042c8fe2:'screen_background'})
class FlashMachine(DiagnosticMachine):
 instruction_budget=20000000
 def __init__(self):
  self.flash=bytearray(b'\xff'*1048576);self.io_calls=0;self.fail_io=0;self.welcome=False;self.welcomes=[];self.bind_calls=0;self.background=255;self.background_calls=0
  super().__init__();self.free_bytes=353656;assert self.build['flash_scene'] and self.build['minimal_launcher']
 def instruction(self,uc,address,size,userdata):
  if address==self.symbols['mm_flash_store_init']:self.flash_context=self.reg(10)
  if address==self.symbols['glassly_flash_broker_bind']:
   self.bind_calls+=1;self.native_write(self.reg(10),struct.pack('<IIII',123,0x05003000,0x05003010,0x05003020));self.native_write(self.reg(11),bytes(32));self.return_native(0);return
  return super().instruction(uc,address,size,userdata)
 def native(self,name,args):
  a0,a1,a2,a3=args[:4]
  if name=='free_bytes':return max(0,self.free_bytes-sum(v['size'] for v in self.allocations.values() if v['live'] and v['tag']=='owned')-9000)
  if name=='base_app' and self.welcome:return 0x0200fcf4
  if name=='welcome_home':self.welcomes.append(a0);return 0
  if name=='screen_background':
   assert a0==self.parent and a1==0 and a2==0 and self.screen_present
   self.background=0;self.background_calls+=1;return 0
  if name=='image_source' and not a1:
   assert a0 in self.images;self.images[a0]['detached']=True;return 0
  if name=='image_source':self.images[a0]['detached']=False
  if name.startswith('store_'):
   assert a0==123 and 0x700000<=a1<0x800000
   self.io_calls+=1
   if self.io_calls==self.fail_io:return 9
   off=a1-0x700000
   if name=='store_read':
    assert 0<a3<=256 and a3<=256-(a1&255);self.native_write(a2,bytes(self.flash[off:off+a3]))
   elif name=='store_erase':assert a2==4096 and not a1%4096;self.flash[off:off+4096]=b'\xff'*4096
   else:
    assert a3==256 and not a1%256;data=self.read(a2,a3);assert all(x&y==y for x,y in zip(self.flash[off:off+a3],data));self.flash[off:off+a3]=data
   return 0
  return super().native(name,args)
 def establish(self):
  reply,_=self.send_scene(S.reset_packet());assert reply[3]==0 and reply[11:13]==b'\x00\x01'
  reply,_=self.send_scene(S.put_packet());assert reply[3]==0
  reply,_=self.send_scene(S.show_packet());assert reply[3]==0 and self.pixel(6,6)==7
 def carrier(self,command,token=7):
  head=lambda op:struct.pack('<BBI',127,op,token)
  packets=[head(0)+struct.pack('<H',len(command))]
  packets += [head(1)+struct.pack('<H',i)+command[i:i+1024] for i in range(0,len(command),1024)]
  packets += [head(2)+struct.pack('<I',zlib.crc32(command))]
  for p in packets[:-1]:
   _,values=self.send_scene(p,patch_epoch=False);assert values[0]['result']=='accepted',values
  return self.send_scene(packets[-1],patch_epoch=False,reply_mode=command[0])
class Tests(unittest.TestCase):
 def test_shared_background_and_absent_screen(self):
  m=FlashMachine();initial=set(m.owned_live())
  m.screen_present=False;m.call('glassly_launcher_init_entry',0xdeadbeef,display=True)
  self.assertEqual(m.background_calls,0)
  m.screen_present=True
  for _ in range(2):
   m.background=255;m.call('glassly_launcher_init_entry',0xdeadbeef,display=True)
   self.assertEqual(m.background,0)
   m.establish();m.send_scene(bytes([11]),patch_epoch=False)
   self.assertEqual(m.background,0)
  self.assertEqual(m.background_calls,2)
  m.call('glassly_launcher_destroy_entry',display=True)
  self.assertEqual(m.background,0)
  self.assertEqual(set(m.owned_live()),initial)
  self.assertFalse(m.images or m.timers)
 def test_minimal_callbacks_and_complete_teardown(self):
  m=FlashMachine();initial=set(m.owned_live())
  for _ in range(2):
   for name in ('init','tick','event','message','suspend'):
    m.call('glassly_launcher_'+name+'_entry',0xdead0000,0xdead0001,0xdead0002,0xdead0003,display=True)
   m.call('glassly_launcher_home_entry',42,display=True)
  self.assertEqual(set(m.owned_live()),initial);self.assertFalse(m.welcomes)
  m.welcome=True;m.call('glassly_launcher_home_entry',43,display=True);self.assertEqual(m.welcomes,[43]);m.welcome=False
  m.establish();m.diagnostic(2);m.send_scene(S.show_packet())
  m.call('glassly_launcher_destroy_entry',display=True)
  self.assertFalse(m.images or m.timers or m.owned_live())
  m.call('glassly_launcher_destroy_entry',display=True);self.assertFalse(m.owned_live())
 def test_identity_and_maximum_carrier(self):
  m=FlashMachine();cap,_=m.service(0x7e)
  self.assertEqual((cap['version'],cap['storeKiB'],cap['maxMessageBytes'],cap['leaseTicks']),('GLASSLYCFW/1',256,65535,30000))
  # Original zero-count bundle intentionally ignores trailing bytes. Exercise
  # every byte through outer ingress without inventing a second scene parser.
  command=bytes([8,0])+bytes((i*37)&255 for i in range(65533))
  _,values=m.carrier(command);self.assertEqual(values[0]['result'],'ok')
  _,values=m.send_scene(struct.pack('<BBII',127,2,7,zlib.crc32(command)),patch_epoch=False)
  self.assertEqual(values[0]['result'],'invalid')
  m.call('glassly_launcher_destroy_entry',display=True);self.assertFalse(m.images or m.owned_live())
 def test_full_asset_capacity_and_storage_fault(self):
  m=FlashMachine();m.send_scene(S.reset_packet())
  font=bytes(384)+bytes((i*17)&255 for i in range(384,262144))
  def asset(offset,data,request=2,asset_id=5):
   return struct.pack('<BHHBIIBIIH',37,m.epoch,request,0,asset_id,1,1,262144,offset,len(data))+data
  for index,off in enumerate(range(0,262144,65510)):
   command=asset(off,font[off:off+65510],index+2)
   reply,values=m.carrier(command,100+index);assert reply is not None,values
   self.assertEqual(reply[3],0,values)
  context=m.flash_context;out=m.allocate(65535,'readback')
  for off in range(0,262144,65535):
   n=min(65535,262144-off);m.call('mm_flash_store_read',context,off,out,n,display=True)
   self.assertEqual(m.reg(10),0);self.assertEqual(m.read(out,n),font[off:off+n])
  m.discard(out)
  before=bytes(m.flash);m.fail_io=m.io_calls+1
  reply,values=m.carrier(asset(0,font[:1024],10,6),111)
  self.assertIsNone(reply);self.assertEqual(values[0]['result'],'storage-error');self.assertEqual(bytes(m.flash),before)
  self.assertTrue(m.images[m.graphics()[0]].get('detached'))
  m.call('glassly_launcher_destroy_entry',display=True);self.assertFalse(m.images or m.owned_live())
 def test_lease_aborts_partial_record(self):
  m=FlashMachine();m.send_scene(struct.pack('<BBIH',127,0,99,65535),patch_epoch=False)
  self.assertTrue(any(v['size']==65535 and v['live'] for v in m.allocations.values()))
  m.tick_at(m.now+30000)
  self.assertFalse(m.images or m.owned_live())
 def test_retained_scene_and_cleanup_epochs(self):
  m=FlashMachine();reply,_=m.send_scene(S.reset_packet());self.assertEqual(reply[11:13],b'\x00\x01')
  m.send_scene(S.put_packet());m.send_scene(S.show_packet());self.assertEqual(m.pixel(6,6),7)
  self.assertEqual(m.bind_calls,1)
  m.send_scene(b'\x0b');m.send_scene(S.reset_packet());self.assertEqual(m.bind_calls,2)
  m.call('glassly_launcher_destroy_entry',display=True);self.assertFalse(m.images or m.owned_live())
def main():
 p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
 G.BUILD=a.build.resolve();build=json.loads((G.BUILD/'build.json').read_text());G.PINNED_SHA=build['blob_sha256'];G.RESULTS.clear();S.STEPS.clear()
 result=unittest.TextTestRunner(verbosity=2,failfast=True).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps({'passed':result.wasSuccessful(),'groups':result.testsRun,'runtime_sha256':G.PINNED_SHA,'calls':G.RESULTS,'steps':S.STEPS,'hardware_tested':False,'mock_boundaries':['Native LVGL/heap/font APIs','Flash broker bind and physical I/O; broker separately tested with actual pthread queues'],'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2)+'\n')
 return 0 if result.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())
