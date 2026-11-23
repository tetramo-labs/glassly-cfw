import Foundation
import CryptoKit
import Darwin
import MemoMindCore
import MemoMindBluetooth
struct Failure:Error{let reason:String}
final class CheckedIO:MemoMindTransport {
 let base:MemoMindTransport;let check:() throws -> Void
 init(_ base:MemoMindTransport,_ check:@escaping () throws -> Void){self.base=base;self.check=check}
 func write(_ data:Data)throws{try check();try base.write(data)}
 func read(timeout:TimeInterval)throws->Data{try check();return try base.read(timeout:timeout)}
}
func need(_ ok:Bool,_ reason:String)throws{if !ok{throw Failure(reason:reason)}}
func sha(_ b:Data)->String{SHA256.hash(data:b).map{String(format:"%02x",$0)}.joined()}
try need(CommandLine.arguments.count==2,"New output directory required")
let output=URL(fileURLWithPath:CommandLine.arguments[1],isDirectory:true)
try need(mkdir(output.path,0o700)==0,"Output must be new")
let fd=open(output.appendingPathComponent("trace.jsonl").path,O_WRONLY|O_CREAT|O_EXCL,0o600)
try need(fd>=0,"Trace creation failed")
let trace=FileHandle(fileDescriptor:fd,closeOnDealloc:true)
func record(_ event:String,_ fields:[String:Any]=[:])throws{
 var r=fields;r["event"]=event;r["utc"]=ISO8601DateFormatter().string(from:Date());r["uptime"]=ProcessInfo.processInfo.systemUptime
 var b=try JSONSerialization.data(withJSONObject:r,options:.sortedKeys);b.append(10);try trace.write(contentsOf:b);try trace.synchronize()
}
func save(_ name:String,_ data:Data)throws{try data.write(to:output.appendingPathComponent(name),options:.withoutOverwriting)}
let transport=MacRFCOMMTransport(traffic:{e in try record(e.kind.rawValue,["hex":e.data.map{String(format:"%02x",$0)}.joined(),"status":e.status as Any? ?? NSNull()])})
do{
 let image=try Data(contentsOf:URL(fileURLWithPath:"captures/firmware/bundle-commands-001/firmware.bin"))
 _=try EligibleFirmware.load(data:image,expectedSHA256:"0f54b4569ef2960e2916abfcff4a434c0f1164f05d059a8418100f3da3f8fce5")
 let expected=try Data(contentsOf:URL(fileURLWithPath:"captures/firmware/bundle-commands-001/expected-app-header.bin"))
 try need(expected.count==256 && sha(expected)=="5a930be718c3937d6c2221fd8953a53edd7bf916a1a0dd588258fcf4161a1d3f","Candidate header pin mismatch")
 try transport.connect(address:"4C:3C:8F:90:CC:C3",service:.normal)
 var notificationError:String?=nil
 let checked=CheckedIO(transport){try need(notificationError==nil,notificationError ?? "Notification validation failed")}
 let session=GMSession(transport:checked);let device=try session.probe();try device.validate(address:"4C:3C:8F:90:CC:C3")
 var notifications:[UInt16]=[]
 var expectedNotifications:[(UInt8,UInt16)]=[]
 func rawJSON(_ message:GMMessage)throws->Data {
  try need(message.tlvs.count==1 && message.tlvs[0].kind==5 && message.tlvs[0].value.count<=1024,"Expected bounded JSON response")
  var raw=message.tlvs[0].value;if raw.last==0{raw.removeLast()};return raw
 }
 func settledTag(_ message:GMMessage)throws->UInt16? {
  guard message.service==15 && message.command==0x7d else{return nil}
  let raw=try rawJSON(message),prefix=Data("{\"glassly\":\"scene\",\"abi\":1,\"result\":\"settled\",\"tag\":".utf8)
  guard raw.starts(with:prefix) else{return nil}
  try need(raw.last==125,"Malformed settled suffix")
  let digits=raw.dropFirst(prefix.count).dropLast()
  try need(!digits.isEmpty && digits.count<=5 && (digits.count==1 || digits.first != 48) && digits.allSatisfy{48...57 ~= $0},"Malformed settled tag")
  guard let tag=UInt16(String(decoding:digits,as:UTF8.self)) else{throw Failure(reason:"Settled tag overflow")}
  return tag
 }
 session.unsolicited={ message in
  do{
   guard let tag=try settledTag(message) else{throw Failure(reason:"Unexpected uncorrelated message")}
   try need(notifications.count<expectedNotifications.count,"Unexpected notification count")
   let wanted=expectedNotifications[notifications.count]
   try need(message.event==wanted.0 && tag==wanted.1,"Unexpected notification event or tag order")
   notifications.append(tag);try record("settled-notification",["eventID":message.event,"tag":tag])
  }catch{notificationError=String(describing:error)}
 }
 var event:UInt8=0x30
 func jsonRequest(_ command:UInt8,_ bytes:Data=Data())throws->Data{
  try need(notificationError==nil,notificationError ?? "Notification validation failed")
  event=event==255 ? 1:event+1
  let message=try session.request(event:event,service:15,command:command,body:bytes.isEmpty ? Data():GMTLV(kind:1,value:bytes).encoded(),responseFilter:{try settledTag($0)==nil})
  try need(notificationError==nil,notificationError ?? "Notification validation failed")
  try need(message.tlvs.count==1 && message.tlvs[0].kind==5 && message.tlvs[0].value.count<=1024,"Expected bounded JSON response")
  var raw=message.tlvs[0].value;if raw.last==0{raw.removeLast()};return raw
 }
 let header=try jsonRequest(0x7b,Data([1,0,0,0xb0,0x1e,0,0,1]))
 let exactHeader="{\"glassly\":\"flash-read\",\"abi\":1,\"result\":\"ok\",\"device\":0,\"offset\":2011136,\"length\":256,\"hex\":\""+expected.map{String(format:"%02x",$0)}.joined()+"\"}"
 try need(header==Data(exactHeader.utf8),"Live header mismatch");try save("header-reply.json",header)
 let caps=try jsonRequest(0x7e);try save("capabilities.json",caps)
 struct Caps:Decodable{let glassly:String;let abi:Int;let profile:String;let width:Int;let height:Int;let modes:[Int];let rasterLens:String;let maxMessageBytes:Int;let bundleModes:[Int];let bundleMaxSegments:Int}
 let c=try JSONDecoder().decode(Caps.self,from:caps)
 try need(c.glassly=="graphics-runtime" && c.abi==1 && c.profile=="H001Y-1.0.3.127" && c.width==600 && c.height==350 && c.modes.contains(3) && c.modes.contains(6) && c.modes.contains(9) && c.modes.contains(8) && c.rasterLens=="first-left" && c.maxMessageBytes==8192 && c.bundleModes==[3,6,9,19,20,36,37,38,39,40,41] && c.bundleMaxSegments==255,"Required bundle capability absent")
 func command(_ data:Data,_ wanted:String="ok")throws{
  let r=try jsonRequest(0x7d,data)
  let presentation = wanted == "ok" ? ",\"presentation\":\"scheduled\"" : ""
  let exact="{\"glassly\":\"graphics\",\"abi\":1,\"result\":\""+wanted+"\""+presentation+"}"
  try need(r==Data(exact.utf8),"Unexpected graphics reply: "+String(decoding:r,as:UTF8.self))
 }
 try command(Data([11]),"cleared")
 try record("cleanup-complete",["clearAcknowledged":true,"hardwarePixelReadback":false])
 transport.close();print("Clear acknowledged after exact image header check")
}catch{try? record("failed",["error":String(describing:error)]);transport.close();fputs("\(error)\n",stderr);exit(1)}
