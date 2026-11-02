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
 let image=try Data(contentsOf:URL(fileURLWithPath:"captures/firmware/reset-undo-trim-001/firmware.bin"))
 try need(image.count==2226404,"Image size mismatch")
 _=try EligibleFirmware.load(data:image,expectedSHA256:"3bf52f5a2a6137759ddc3546c47b1ceed42a401953e75379712044d32e2206a9")
 let runtime=try Data(contentsOf:URL(fileURLWithPath:"runtime/build/reset-undo-trim-003/graphics.bin"))
 try need(runtime.count==60256 && sha(runtime)=="93040b1de94b52b710d7a3e37a3adef2f1e840108fb53ab69b9ecf46e14102f4","Runtime pin mismatch")
 let expected=try Data(contentsOf:URL(fileURLWithPath:"captures/firmware/reset-undo-trim-001/expected-app-header.bin"))
 try need(expected.count==256 && sha(expected)=="76d7bfc287aad7294d4d855a86d4d2cfbe8043a3b555eca41a891e17b1f7a4e6","Candidate header pin mismatch")
 try transport.connect(address:"4C:3C:8F:90:CC:C3",service:.normal)
 var notificationError:String?=nil
 let checked=CheckedIO(transport){try need(notificationError==nil,notificationError ?? "Notification failure")}
 let session=GMSession(transport:checked)
 let device=try session.probe();try device.validate(address:"4C:3C:8F:90:CC:C3");try need(device.firmwareVersion=="1.0.3.127","Expected installed firmware");try save("device.json",JSONEncoder().encode(device))
 session.unsolicited={message in do{
  try need(message.service != 15,"Unexpected reserved-service reply")
  try record("native-service-notification",["eventID":message.event,"service":message.service,"command":message.command,"bodyHex":message.body.map{String(format:"%02x",$0)}.joined()])
 }catch{notificationError=String(describing:error)}}
 var event:UInt8=0x30
 func request(_ command:UInt8,_ data:Data=Data())throws->GMMessage{
  try need(notificationError==nil,notificationError ?? "Notification failure")
  event=event==255 ? 1:event+1
  let message=try session.request(event:event,service:15,command:command,body:data.isEmpty ? Data():GMTLV(kind:1,value:data).encoded(),responseFilter:{_ in true})
  try need(notificationError==nil,notificationError ?? "Notification failure")
  return message
 }
 func raw(_ message:GMMessage)throws->Data{
  try need(message.tlvs.count==1 && message.tlvs[0].kind==5 && message.tlvs[0].value.count<=1024,"JSON TLV bound")
  var data=message.tlvs[0].value;if data.last==0{data.removeLast()};return data
 }
 func exact(_ message:GMMessage,_ wanted:String)throws{try need(raw(message)==Data(wanted.utf8),"Unexpected reply")}
 let header=try raw(request(0x7b,Data([1,0,0,0xb0,0x1e,0,0,1])))
 let exactHeader="{\"glassly\":\"flash-read\",\"abi\":1,\"result\":\"ok\",\"device\":0,\"offset\":2011136,\"length\":256,\"hex\":\""+expected.map{String(format:"%02x",$0)}.joined()+"\"}"
 try need(header==Data(exactHeader.utf8),"Live header mismatch");try save("header-reply.json",header)

 func graphics(_ data:Data,_ result:String="ok")throws{
  let extra=result=="ok" ? ",\"presentation\":\"scheduled\"":""
  try exact(request(0x7d,data),"{\"glassly\":\"graphics\",\"abi\":1,\"result\":\""+result+"\""+extra+"}")
 }
 var cleanupNeeded=false
 defer {if cleanupNeeded {do{try graphics(Data([11]),"cleared");try record("failure-cleanup-complete")}catch{try? record("failure-cleanup-failed",["error":String(describing:error)])}}}
 var epoch:UInt16=0
 func scene(_ mode:UInt8,_ number:UInt16)throws{
  var packet=Data([mode,UInt8(truncatingIfNeeded:epoch),UInt8(epoch>>8),UInt8(truncatingIfNeeded:number),UInt8(number>>8)])
  if mode==41{packet.append(0)}else{
   packet.append(contentsOf:[1,1,0,0,0,1,0,0,0,3,1,7,0,5,0,5,0,10,0,5,0,0,0,0,0,0,0,0,0])
  }
  let rawReply=try raw(request(0x7d,packet))
  let prefix=Data("{\"glassly\":\"scene\",\"abi\":1,\"result\":\"ok\",\"replyHex\":\"".utf8)
  try need(rawReply.starts(with:prefix) && rawReply.suffix(2)==Data([34,125]),"Scene reply framing")
  let text=Array(rawReply.dropFirst(prefix.count).dropLast(2)),count=mode==41 ? 26:22
  try need(text.count==count && text.allSatisfy{48...57 ~= $0 || 97...102 ~= $0},"Scene reply hex")
  func nibble(_ b:UInt8)->UInt8{b<58 ? b-48:b-87}
  let b=stride(from:0,to:count,by:2).map{nibble(text[$0])*16+nibble(text[$0+1])}
  let receivedEpoch=UInt16(b[4])|UInt16(b[5])<<8
  try need(b[0]==mode && UInt16(b[1])|UInt16(b[2])<<8==number && b[3]==0 && receivedEpoch != 0 && b[10]==0,"Scene correlation/status")
  if mode==41{try need(b[6...9].allSatisfy{$0==0} && b[11]==64 && b[12]==0,"RESET revision/capacity")}else{try need(receivedEpoch==epoch && b[6]==1 && b[7...9].allSatisfy{$0==0},"PUT revision/epoch")}
  epoch=receivedEpoch
  try save("scene-\(number).json",rawReply);try record("scene-command",["mode":mode,"requestID":number,"epoch":epoch,"eventID":event,"packetHex":packet.map{String(format:"%02x",$0)}.joined()])
 }
 var samples:[[String:Any]]=[]
 func sample(_ phase:String,_ index:Int)throws{
  try graphics(Data([36,0]))
  let caps=try raw(request(0x7e));try save("\(phase)-\(index).json",caps)
 struct Caps:Decodable{let glassly:String;let abi:Int;let profile:String;let width:Int;let height:Int;let modes:[Int];let diagnostics:String;let snapshotBytes:Int;let cleanup:String;let maxMessageBytes:Int;let storeKiB:Int;let textMaxBytes:Int;let textFont:String;let missingGlyph:String;let emptyGeometry:String;let bundleModes:[Int];let freeBytesHex:String;let lowWaterBytesHex:String}
 let c=try JSONDecoder().decode(Caps.self,from:caps)
 try need(c.glassly=="graphics-runtime" && c.abi==1 && c.profile=="H001Y-1.0.3.127" && c.width==600 && c.height==350 && c.modes==[3,6,7,8,9,11,15,19,20,36,37,38,39,40,41] && c.diagnostics=="native-v1" && c.snapshotBytes==20 && c.cleanup=="graphics-input-current-screen" && c.maxMessageBytes==8192 && c.storeKiB==64 && c.textMaxBytes==255 && c.textFont=="native-resource" && c.missingGlyph=="reject" && c.emptyGeometry=="lease-only" && c.bundleModes==[3,6,9,15,19,20,36,37,38,39,40,41],"Required diagnostics capabilities absent")
 // Exact native canonical capabilities reject duplicate/escaped-key ambiguity.
 for h in [c.freeBytesHex,c.lowWaterBytesHex]{try need(h.utf8.count==8 && h.utf8.allSatisfy{48...57 ~= $0 || 97...102 ~= $0},"Heap snapshot syntax")}
 let exactCaps="{\"glassly\":\"graphics-runtime\",\"abi\":1,\"profile\":\"H001Y-1.0.3.127\",\"width\":600,\"height\":350,\"flashRead\":123,\"inputObserver\":{\"command\":124,\"capacity\":32,\"leaseTicks\":30000},\"modes\":[3,6,7,8,9,11,15,19,20,36,37,38,39,40,41],\"diagnostics\":\"native-v1\",\"snapshotBytes\":20,\"cleanup\":\"graphics-input-current-screen\",\"rasterLens\":\"first-left\",\"bundleModes\":[3,6,9,15,19,20,36,37,38,39,40,41],\"bundleMaxSegments\":255,\"textMaxBytes\":255,\"textFont\":\"native-resource\",\"missingGlyph\":\"reject\",\"maxMessageBytes\":8192,\"storeKiB\":64,\"builtinText\":true,\"emptyGeometry\":\"lease-only\",\"maxGeometryRecords\":255,\"leaseTicks\":1000,\"tickMs\":1,\"flashCanary\":122,\"registryBytes\":256,\"writableStaticBytes\":256,\"freeBytesHex\":\"\(c.freeBytesHex)\",\"lowWaterBytesHex\":\"\(c.lowWaterBytesHex)\"}"
 try need(caps==Data(exactCaps.utf8),"Unexpected capabilities schema")
  guard let free=UInt32(c.freeBytesHex,radix:16),let low=UInt32(c.lowWaterBytesHex,radix:16) else {throw Failure(reason:"Invalid heap hexadecimal value")}

  let item:[String:Any]=["phase":phase,"index":index,"eventID":event,"freeBytes":free,"lowWaterBytes":low]
  samples.append(item);try record("heap-sample",item)
  RunLoop.current.run(until:Date().addingTimeInterval(0.1))
 }
 try record("scratch-probe-intent",["release":"reset-undo-trim-001","samplesPerPhase":10,"noCanaryOrOTA":true,"mutationScope":"RAM RESET/PUT, lease renewal and cleanup only"])
 try graphics(Data([11]),"cleared");cleanupNeeded=true
 try scene(41,1);try scene(37,2)
 for i in 0..<10{try sample("put",i)}
 try scene(41,3)
 for i in 0..<10{try sample("reset",i)}
 try scene(37,4)
 for i in 0..<10{try sample("reacquired",i)}
 try graphics(Data([11]),"cleared");cleanupNeeded=false
 try save("capabilities-after-cleanup.json",raw(request(0x7e)))
 let result:[String:Any]=["complete":true,"release":"reset-undo-trim-001","appHeaderSHA256":sha(expected),"samples":samples,"cleanupVerified":true,"physicalOutputConfirmed":false,"flashMutations":0,"otaCommands":0]
 try save("result.json",JSONSerialization.data(withJSONObject:result,options:[.prettyPrinted,.sortedKeys]));try record("scratch-probe-complete")
 transport.close();print(String(decoding:try JSONSerialization.data(withJSONObject:result,options:[.prettyPrinted,.sortedKeys]),as:UTF8.self))
}catch{try? record("failed",["error":String(describing:error)]);transport.close();fputs("\(error)\n",stderr);exit(1)}
