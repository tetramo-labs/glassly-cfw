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
 let image=try Data(contentsOf:URL(fileURLWithPath:"captures/firmware/diagnostic-commands-001/firmware.bin"))
 try need(image.count==1,"Image size mismatch")
 _=try EligibleFirmware.load(data:image,expectedSHA256:"0000000000000000000000000000000000000000000000000000000000000000")
 let runtime=try Data(contentsOf:URL(fileURLWithPath:"runtime/build/diagnostic-commands-001/graphics.bin"))
 try need(runtime.count==1 && sha(runtime)=="0000000000000000000000000000000000000000000000000000000000000000","Runtime pin mismatch")
 let expected=try Data(contentsOf:URL(fileURLWithPath:"captures/firmware/diagnostic-commands-001/expected-app-header.bin"))
 try need(expected.count==256 && sha(expected)=="0000000000000000000000000000000000000000000000000000000000000000","Candidate header pin mismatch")
 try transport.connect(address:"4C:3C:8F:90:CC:C3",service:.normal)
 var notificationError:String?=nil
 let checked=CheckedIO(transport){try need(notificationError==nil,notificationError ?? "Notification failure")}
 let session=GMSession(transport:checked)
 let device=try session.probe();try device.validate(address:"4C:3C:8F:90:CC:C3")
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
 let caps=try raw(request(0x7e));try save("capabilities.json",caps)
 struct Caps:Decodable{let glassly:String;let abi:Int;let profile:String;let width:Int;let height:Int;let modes:[Int];let diagnostics:String;let snapshotBytes:Int;let cleanup:String;let maxMessageBytes:Int;let storeKiB:Int;let textMaxBytes:Int;let textFont:String;let missingGlyph:String;let emptyGeometry:String;let bundleModes:[Int];let freeBytesHex:String;let lowWaterBytesHex:String}
 let c=try JSONDecoder().decode(Caps.self,from:caps)
 try need(c.glassly=="graphics-runtime" && c.abi==1 && c.profile=="H001Y-1.0.3.127" && c.width==600 && c.height==350 && c.modes==[3,6,7,8,9,11,15,19,20,36,37,38,39,40,41] && c.diagnostics=="native-v1" && c.snapshotBytes==20 && c.cleanup=="graphics-input-current-screen" && c.maxMessageBytes==8192 && c.storeKiB==64 && c.textMaxBytes==255 && c.textFont=="native-resource" && c.missingGlyph=="reject" && c.emptyGeometry=="lease-only" && c.bundleModes==[3,6,9,15,19,20,36,37,38,39,40,41],"Required diagnostics capabilities absent")
 // Exact native canonical capabilities reject duplicate/escaped-key ambiguity.
 for h in [c.freeBytesHex,c.lowWaterBytesHex]{try need(h.utf8.count==8 && h.utf8.allSatisfy{48...57 ~= $0 || 97...102 ~= $0},"Heap snapshot syntax")}
 let exactCaps="{\"glassly\":\"graphics-runtime\",\"abi\":1,\"profile\":\"H001Y-1.0.3.127\",\"width\":600,\"height\":350,\"flashRead\":123,\"inputObserver\":{\"command\":124,\"capacity\":32,\"leaseTicks\":30000},\"modes\":[3,6,7,8,9,11,15,19,20,36,37,38,39,40,41],\"diagnostics\":\"native-v1\",\"snapshotBytes\":20,\"cleanup\":\"graphics-input-current-screen\",\"rasterLens\":\"first-left\",\"bundleModes\":[3,6,9,15,19,20,36,37,38,39,40,41],\"bundleMaxSegments\":255,\"textMaxBytes\":255,\"textFont\":\"native-resource\",\"missingGlyph\":\"reject\",\"maxMessageBytes\":8192,\"storeKiB\":64,\"builtinText\":true,\"emptyGeometry\":\"lease-only\",\"maxGeometryRecords\":255,\"leaseTicks\":1000,\"tickMs\":1,\"flashCanary\":122,\"registryBytes\":256,\"writableStaticBytes\":256,\"freeBytesHex\":\"\(c.freeBytesHex)\",\"lowWaterBytesHex\":\"\(c.lowWaterBytesHex)\"}"
 try need(caps==Data(exactCaps.utf8),"Unexpected capabilities schema")
 func command(_ data:Data,_ result:String="ok")throws{
  let suffix=result=="ok" ? ",\"presentation\":\"scheduled\"":""
  try exact(request(0x7d,data),"{\"glassly\":\"graphics\",\"abi\":1,\"result\":\""+result+"\""+suffix+"}")
 }
 func snapshot(_ label:String,_ data:Data=Data([7,255]))throws->DiagnosticSnapshot{
  let value=try DiagnosticSnapshot.decode(request(0x7d,data),expectedEvent:event)
  let fields=try JSONSerialization.jsonObject(with:JSONEncoder().encode(value))
  try record("diagnostic-snapshot",["label":label,"eventID":event,"snapshot":fields]);return value
 }
 func expect(_ s:DiagnosticSnapshot,_ flags:UInt8,_ hidden:Bool,_ seen:Bool,_ resync:Bool,_ last:UInt16,_ high:UInt16,_ worker:UInt32=0,_ failed:UInt8=0,_ epoch:UInt16?=nil)throws{
  try need(s.flags==flags && s.hidden==hidden && s.seen==seen && s.resync==resync && s.lastFrameID==last && s.highFrameID==high && s.displayWorkerFailures==worker && s.displayAllocationFailures==0 && s.lastFailedMode==failed && (epoch==nil || s.savedSceneEpoch==epoch),"Unexpected diagnostic state")
 }
 func next(_ epoch:UInt16)->UInt16{epoch==65535 ? 1:epoch+1}
 func reset(_ requestID:UInt16)throws->UInt16{
  let reply=try raw(request(0x7d,Data([41,0,0,UInt8(truncatingIfNeeded:requestID),UInt8(requestID>>8),0,250])))
  let prefix=Data("{\"glassly\":\"scene\",\"abi\":1,\"result\":\"ok\",\"replyHex\":\"".utf8)
  try need(reply.starts(with:prefix) && reply.suffix(2)==Data([34,125]),"Scene JSON framing")
  let text=Array(reply.dropFirst(prefix.count).dropLast(2));try need(text.count==26 && text.allSatisfy{48...57 ~= $0 || 97...102 ~= $0},"Scene hex")
  func n(_ b:UInt8)->UInt8{b<58 ? b-48:b-87}
  let b=stride(from:0,to:26,by:2).map{n(text[$0])*16+n(text[$0+1])}
  let epoch=UInt16(b[4])|UInt16(b[5])<<8
  try need(b[0]==41 && (UInt16(b[1])|UInt16(b[2])<<8)==requestID && b[3]==0 && epoch != 0 && b[10]==0 && b[11]==64 && b[12]==0,"Scene RESET correlation")
  try record("scene-reset",["request":requestID,"epoch":epoch]);return epoch
 }
 let nonce:UInt32=0x47414944
 func input(_ subscribe:Bool=false)throws{
  let body=subscribe ? Data([1,1,1,0x44,0x49,0x41,0x47]):Data([1,0])
  let message=try request(0x7c,body)
  let expected="{\"glassly\":\"input\",\"abi\":1,\"result\":\"ok\",\"active\":"+(subscribe ? "true":"false")+",\"nonce\":"+String(subscribe ? nonce:0)+",\"mask\":"+(subscribe ? "1":"0")+",\"capacity\":32,\"leaseTicks\":30000,\"sequence\":0,\"ack\":0,\"drops\":0,\"exhausted\":false,\"records\":[]}"
  try exact(message,expected);try record("input-observer",["active":subscribe,"mask":subscribe ? 1:0])
 }
 try command(RasterCommands.cleanupSession(),"cleared");try input()
 let epoch=try reset(1)
 let base=try snapshot("clear",RasterCommands.diagnostics(.clear));try expect(base,0,true,false,false,0,0)
 try need(epoch==next(base.savedSceneEpoch),"Initial RESET epoch chain")
 try need(snapshot("missing-sub",Data([7]))==base,"Missing sub changed state")
 try need(snapshot("unknown-high-trailing",Data([135,255,1,2]))==base,"Unknown sub changed state")
 let black=try RasterCommands.fullFrame(pixels:Data(repeating:0,count:105000));try save("black-frame-command.bin",black)
 func key()throws{try command(black)}
 func delta(_ fid:UInt16)throws{try command(RasterCommands.boundingBox(pixels:Data(repeating:0,count:4),x:0,y:0,width:4,height:2,frameID:fid))}
 try key();try expect(snapshot("key-resync"),0,true,true,true,0,0)
 try delta(10);try expect(snapshot("frame10"),0,true,true,false,10,10)
 try delta(12);try expect(snapshot("frame12"),2,true,true,false,12,12)
 try delta(12);try expect(snapshot("duplicate12"),6,true,true,false,12,12)
 try delta(11);try expect(snapshot("reorder11"),7,true,true,false,11,12)
 try key();try expect(snapshot("key-preserves-ring"),7,true,true,true,11,12)
 try delta(12);try expect(snapshot("duplicate-after-key"),7,true,true,true,11,12)
 try delta(13);try expect(snapshot("resynced13"),7,true,true,false,13,13)
 let title=try RasterCommands.builtinText("DIAG",x:80,y:100,options:31);try save("title-command.bin",title)
 try expect(snapshot("show-high-trailing",Data([135,2,255])),7,false,true,false,13,13)
 try command(title) // First actual presentation after show.
 try expect(snapshot("hide-trailing",Data([7,1,255])),7,true,true,false,13,13)
 try command(title) // First actual presentation after hide.
 try expect(snapshot("show-before-failure",RasterCommands.diagnostics(.show)),7,false,true,false,13,13)
 // Full header passes admission; zero width fails actual scene raster dispatch.
 let invalidCopy=Data([9])+Data(count:16)
 try command(invalidCopy,"invalid");try expect(snapshot("worker-failure"),7,false,true,false,13,13,1,9)
 try input(true)
 try command(Data([139,0,255]),"cleared")
 try expect(snapshot("cleanup-saved-epoch"),7,true,true,false,13,13,1,9,next(epoch));try input()
 try command(Data([11,255]),"cleared")
 try expect(snapshot("cleanup-idempotent"),7,true,true,false,13,13,1,9,next(epoch));try input()
 let second=try reset(2);try need(second==next(next(epoch)),"RESET after cleanup lost epoch")
 try key()
 try expect(snapshot("show-before-present",RasterCommands.diagnostics(.show)),7,false,true,true,13,13,1,9,next(epoch))
 try command(title)
 try record("pattern-visible",["description":"DIAG on black with separate compact diagnostics overlay; overlay may show R/S/D, frame13/high13 and worker1/allocation0","hardwarePixelReadback":false,"immediateShowHideRefreshProven":false])
 let deadline=ProcessInfo.processInfo.systemUptime+300,finishURL=output.appendingPathComponent("finish-requested.json")
 while ProcessInfo.processInfo.systemUptime<deadline && !FileManager.default.fileExists(atPath:finishURL.path){
  RunLoop.current.run(until:Date(timeIntervalSinceNow:0.25));try transport.checkHealth();try command(Data([36,0]))
 }
 try record("hold-ended",["finishRequested":FileManager.default.fileExists(atPath:finishURL.path)])
 try command(RasterCommands.cleanupSession(),"cleared")
 try expect(snapshot("final-cleanup"),7,true,true,true,13,13,1,9,next(second));try input()
 try record("smoke-complete",["cleared":true,"observerInactive":true,"hardwarePixelReadback":false,"continuousPixelRetentionProven":false])
 transport.close();print("Diagnostics state/cleanup acknowledged. Overlay and DIAG visibility require separate user confirmation.")
}catch{try? record("failed",["error":String(describing:error)]);transport.close();fputs("\(error)\n",stderr);exit(1)}
