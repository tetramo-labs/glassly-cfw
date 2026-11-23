import Foundation
import MemoMindCore
 func isDeviceStatusNotice(_ message:GMMessage)->Bool {
  message.service==1 && message.command==0x3a && message.tlvs==[GMTLV(kind:8,value:Data([0]))]
 }

var count=0
for service:UInt8 in [1,2,15] {for command:UInt8 in [0x30,0x3a,0x3b,0x7d] {for kind:UInt8 in [5,8] {for value:UInt8 in [0,1,2] {
 let body=try GMTLV(kind:kind,value:Data([value])).encoded()
 let wire=try GMCodec.frames(event:7,service:service,command:command,body:body).reduce(Data(),+)
 let m=try GMStream().feed(wire)[0]
 precondition(isDeviceStatusNotice(m)==(service==1 && command==0x3a && kind==8 && value==0));count+=1
}}}}
for values in [Data(),Data([0,0])] {
 let wire=try GMCodec.frames(event:7,service:1,command:0x3a,body:GMTLV(kind:8,value:values).encoded()).reduce(Data(),+)
 do { let message=try GMStream().feed(wire)[0];precondition(!isDeviceStatusNotice(message)) } catch { /* Strict fixed-width parser rejects malformed TLV. */ };count+=1
}
print("Status predicate checks passed: \(count)")
