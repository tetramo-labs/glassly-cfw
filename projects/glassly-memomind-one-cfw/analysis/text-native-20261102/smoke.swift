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
 let image=try Data(contentsOf:URL(fileURLWithPath:"captures/firmware/text-commands-001/firmware.bin"))
 _=try EligibleFirmware.load(data:image,expectedSHA256:"e5409e0d42da0009b759852289915e92517a185c1255ad8de28a56c49c070d31")
 let expected=try Data(contentsOf:URL(fileURLWithPath:"captures/firmware/text-commands-001/expected-app-header.bin"))
 try need(expected.count==256 && sha(expected)=="b7e85bb1ca5658d743190e4589da2d7454d41ecad0ca459695a43b36264e6fc0","Candidate header pin mismatch")
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
   if message.service != 15 {
    try record("native-service-notification",["eventID":message.event,"service":message.service,"command":message.command,"bodyHex":message.body.map{String(format:"%02x",$0)}.joined()]);return
   }
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
 struct Caps:Decodable{let glassly:String;let abi:Int;let profile:String;let width:Int;let height:Int;let modes:[Int];let rasterLens:String;let maxMessageBytes:Int;let bundleModes:[Int];let bundleMaxSegments:Int;let textMaxBytes:Int;let textFont:String;let missingGlyph:String}
 let c=try JSONDecoder().decode(Caps.self,from:caps)
 try need(c.glassly=="graphics-runtime" && c.abi==1 && c.profile=="H001Y-1.0.3.127" && c.width==600 && c.height==350 && c.modes.contains(3) && c.modes.contains(6) && c.modes.contains(9) && c.modes.contains(8) && c.rasterLens=="first-left" && c.maxMessageBytes==8192 && c.bundleModes==[3,6,9,15,19,20,36,37,38,39,40,41] && c.modes.contains(15) && c.textMaxBytes==255 && c.textFont=="native-resource" && c.missingGlyph=="reject" && c.bundleMaxSegments==255,"Required text capability absent")
 func command(_ data:Data,_ wanted:String="ok")throws{
  let r=try jsonRequest(0x7d,data)
  let presentation = wanted == "ok" ? ",\"presentation\":\"scheduled\"" : ""
  let exact="{\"glassly\":\"graphics\",\"abi\":1,\"result\":\""+wanted+"\""+presentation+"}"
  try need(r==Data(exact.utf8),"Unexpected graphics reply: "+String(decoding:r,as:UTF8.self))
 }
 // A full black frame establishes a known background using the existing decoder.
 let black=try RasterCommands.fullFrame(pixels:Data(repeating:0,count:105000))
 try save("black-frame-command.bin",black);try command(black)
 // Maximum byte-count uses248 zero-distance controls followed by7 ASCII bytes.
 let maximum=Data(repeating:11,count:248)+Data("TEXT 15".utf8)
 let left=try RasterCommands.builtinText(bytes:maximum,x:70,y:100,options:31)
 try save("maximum-text-command.bin",left);try command(left)
 var highbit=try RasterCommands.builtinText("SWIFT",x:70,y:145,options:31);highbit[0]=0x8f
 try save("highbit-text-command.bin",highbit);try command(highbit)
 let right=try RasterCommands.builtinText("TEXT 15",x:320,y:100,options:31)
 let rightSub=try RasterCommands.builtinText("SWIFT",x:320,y:145,options:31)
 let bundled=try RasterCommands.bundle([right,rightSub]);try save("text-bundle.bin",bundled);try command(bundled)
 let empty=try RasterCommands.builtinText("",x:-32768,y:32767,options:255)
 try save("empty-text-command.bin",empty);try command(empty)
 // Construct malformed wire payloads directly; the typed encoder refuses them.
 let invalid:[Data]=[
  Data([15,0,0,0,0,31,1,0]),
  Data([15,0,0,0,0,31,2,0xc0,0xaf]),
  Data([15,0,0,0,0,31,3,0xed,0xa0,0x80]),
  Data([15,0,0,0,0,31,1]),
  Data([15,0,0,0,0,31,0,65]),
  Data([15,0,0,0,0,31])
 ]
 for (i,data) in invalid.enumerated(){try save("invalid-text-\(i).bin",data);try command(data,"invalid")}
 try record("pattern-visible",["description":"Two native-font TEXT 15 / SWIFT groups on black; left uses direct/highbit commands, right uses mode8 bundle","hardwarePixelReadback":false])
 let deadline=ProcessInfo.processInfo.systemUptime+300
 let finishURL=output.appendingPathComponent("finish-requested.json")
 while ProcessInfo.processInfo.systemUptime<deadline && !FileManager.default.fileExists(atPath:finishURL.path){
  RunLoop.current.run(until:Date(timeIntervalSinceNow:0.25));try transport.checkHealth();try command(Data([36,0]))
 }
 try record("hold-ended",["finishRequested":FileManager.default.fileExists(atPath:finishURL.path)])
 try command(Data([11]),"cleared")
 try record("smoke-complete",["maximumTextAcknowledged":true,"highbitTextAcknowledged":true,"textBundleAcknowledged":true,"invalidCommandsRejected":invalid.count,"cleared":true,"hardwarePixelReadback":false])
 transport.close();print("Native text commands acknowledged; malformed text rejected; display cleared. Visibility requires separate user confirmation.")
}catch{try? record("failed",["error":String(describing:error)]);transport.close();fputs("\(error)\n",stderr);exit(1)}
