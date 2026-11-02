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
 struct Caps:Decodable{let glassly:String;let abi:Int;let profile:String;let width:Int;let height:Int;let modes:[Int];let rasterLens:String;let maxMessageBytes:Int;let bundleModes:[Int];let bundleMaxSegments:Int}
 let c=try JSONDecoder().decode(Caps.self,from:caps)
 try need(c.glassly=="graphics-runtime" && c.abi==1 && c.profile=="H001Y-1.0.3.127" && c.width==600 && c.height==350 && c.modes.contains(3) && c.modes.contains(6) && c.modes.contains(9) && c.modes.contains(8) && c.rasterLens=="first-left" && c.maxMessageBytes==8192 && c.bundleModes==[3,6,9,19,20,36,37,38,39,40,41] && c.bundleMaxSegments==255,"Required bundle capability absent")
 func command(_ data:Data,_ wanted:String="ok")throws{
  let r=try jsonRequest(0x7d,data)
  let presentation = wanted == "ok" ? ",\"presentation\":\"scheduled\"" : ""
  let exact="{\"glassly\":\"graphics\",\"abi\":1,\"result\":\""+wanted+"\""+presentation+"}"
  try need(r==Data(exact.utf8),"Unexpected graphics reply: "+String(decoding:r,as:UTF8.self))
 }
 func le16(_ n:UInt16)->Data {Data([UInt8(truncatingIfNeeded:n),UInt8(n>>8)])}
 func sceneReply(_ data:Data,_ mode:UInt8,_ request:UInt16,_ epoch:UInt16?=nil)throws->UInt16 {
  let raw=try jsonRequest(0x7d,data)
  let prefix=Data("{\"glassly\":\"scene\",\"abi\":1,\"result\":\"ok\",\"replyHex\":\"".utf8),suffix=Data("\"}".utf8)
  try need(raw.starts(with:prefix) && raw.suffix(2)==suffix,"Expected exact scene reply wrapper")
  let h=Array(raw.dropFirst(prefix.count).dropLast(2));try need(h.count>=20 && h.count<=500 && h.count%2==0 && h.allSatisfy{48...57 ~= $0 || 97...102 ~= $0},"Invalid scene reply hex")
  var bytes:[UInt8]=[];for i in stride(from:0,to:h.count,by:2){bytes.append(UInt8(String(decoding:h[i...i+1],as:UTF8.self),radix:16)!)}
  let currentEpoch=UInt16(bytes[4])|UInt16(bytes[5])<<8
  try need(bytes[0]==mode && (UInt16(bytes[1])|UInt16(bytes[2])<<8)==request && bytes[3]==0 && currentEpoch>0 && (epoch==nil || epoch==currentEpoch),"Scene reply correlation/status mismatch")
  if mode==41 {try need(bytes.count==13 && bytes[11]==64 && bytes[12]==0,"RESET store size mismatch")}else{try need(bytes.count==11,"Unexpected applied reply size")}
  try need(bytes[10]==0,"Unexpected eviction count")
  try save("scene-reply-\(request).json",raw);return currentEpoch
 }
 let reset=Data([41,0,0,1,0,0,250]);try save("reset-command.bin",reset)
 let epoch=try sceneReply(reset,41,1)
 func hide(_ request:UInt16)->Data {Data([39])+le16(epoch)+le16(request)+Data([4,0])}
 let tags:[UInt16]=[11,12,11,12,13,14,15,16]
 let tagBundle=try RasterCommands.bundle(tags.map(hide));try save("tags-bundle.bin",tagBundle)
 expectedNotifications += tags.map{(event==255 ? 1:event+1,$0)}
 _=try sceneReply(tagBundle,39,16,epoch)
 try command(Data([36,0]));try need(notifications==tags,"Missing/reordered/duplicated bundle notifications")
 let invalidCopy=Data([9])+le16(0)+le16(0)+le16(0)+le16(1)+le16(0)+le16(0)+le16(1)+le16(1)
 let lateFailure=try RasterCommands.bundle([hide(17),invalidCopy]);try save("late-failure-bundle.bin",lateFailure)
 expectedNotifications.append((event==255 ? 1:event+1,17))
 try command(lateFailure,"invalid");try command(Data([36,0]))
 try need(notifications==tags+[17],"Failed bundle lost or reordered settled notification")
 var frame=Data(repeating:0,count:105000)
 let letters=[["11110","10001","10001","11110","10001","10001","11110"],["01110","10001","10001","01110","10001","10001","01110"]]
 for (letter,rows) in letters.enumerated(){for (row,line) in rows.enumerated(){for (col,b) in line.utf8.enumerated() where b==49{for dy in 0..<6{for dx in 0..<6{
  let x=100+letter*42+col*6+dx,y=100+row*6+dy,index=y*300+x/2
  frame[index]=x%2==0 ? (frame[index]&15)|0xf0 : (frame[index]&240)|15
 }}}}}
 let keyframe=try RasterCommands.fullFrame(pixels:frame);try save("keyframe-command.bin",keyframe);try save("expected-keyframe.gray4",frame)

 var box=Data(repeating:0,count:64*32/2)
 for y in 0..<32{for x in stride(from:0,to:64,by:2){box[y*32+x/2]=((x/8+y/8)%2==0) ? 0xff:0}}
 let delta=try RasterCommands.boundingBox(pixels:box,x:100,y:180,width:64,height:32,frameID:1)
 try save("delta-command.bin",delta)
 for y in 0..<32{frame.replaceSubrange((180+y)*300+50..<(180+y)*300+82,with:box[y*32..<(y+1)*32])}
 try save("expected-seed.gray4",frame)
 func copyPixels(_ source:Data,_ sx:Int,_ sy:Int,_ dx:Int,_ dy:Int,_ width:Int,_ height:Int)->Data {
  var result=source
  for y in 0..<height {for x in 0..<width {
   let si=(sy+y)*300+(sx+x)/2,di=(dy+y)*300+(dx+x)/2
   let color=(sx+x)%2==0 ? source[si]>>4:source[si]&15
   result[di]=(dx+x)%2==0 ? (result[di]&15)|(color<<4):(result[di]&240)|color
  }}
  return result
 }
 // Overlap by one pixel in both directions, including odd source width.
 let overlap=try RasterCommands.rectangleCopy(source:RasterRectangle(x:100,y:180,width:63,height:31),destination:RasterRectangle(x:101,y:181,width:63,height:31))
 try save("overlap-command.bin",overlap)
 frame=copyPixels(frame,100,180,101,181,63,31)
 try save("expected-overlap.gray4",frame)
 // Copy text plus updated checkerboard from odd boundaries to a separate area.
 let copied=try RasterCommands.rectangleCopy(source:RasterRectangle(x:99,y:99,width:129,height:115),destination:RasterRectangle(x:301,y:99,width:129,height:115))
 try save("copy-command.bin",copied)
 frame=copyPixels(frame,99,99,301,99,129,115)
 try save("expected-final.gray4",frame)
 let visualBundle=try RasterCommands.bundle([keyframe,delta,overlap,copied]);try save("visual-bundle.bin",visualBundle);try command(visualBundle)
 let empty=Data([0x88,0,0xab,0xcd]);try save("empty-bundle.bin",empty);try command(empty)
 let invalidBundles=[Data([8,1,2,0,8,0]),Data([8,1,1,0,11]),Data([8,1,1,0,15]),Data([8,1,17,0,9])]
 for (i,bad) in invalidBundles.enumerated(){try save("invalid-bundle-\(i).bin",bad);try command(bad,"invalid")}
 try record("pattern-visible",["description":"Two B8/checkerboard groups on black; drawn by one mode8 bundle","hardwarePixelReadback":false])
 // Existing empty-geometry lease renewals hold the image while the user views it.
 let deadline=ProcessInfo.processInfo.systemUptime+300
 let finishURL=output.appendingPathComponent("finish-requested.json")
 while ProcessInfo.processInfo.systemUptime<deadline && !FileManager.default.fileExists(atPath:finishURL.path){
  RunLoop.current.run(until:Date(timeIntervalSinceNow:0.25));try transport.checkHealth();try command(Data([36,0]))
 }
 try record("hold-ended",["finishRequested":FileManager.default.fileExists(atPath:finishURL.path)])
 try command(Data([11]),"cleared")
 try record("smoke-complete",["keyframeAcknowledged":true,"deltaAcknowledged":true,"invalidCommandsRejected":5,"bundleAcknowledged":true,"settledTags":notifications,"cleared":true,"hardwarePixelReadback":false])
 transport.close();print("Mode8 bundles and settled notifications checked; invalid commands rejected; pattern cleared. Physical visibility needs user confirmation.")
}catch{try? record("failed",["error":String(describing:error)]);transport.close();fputs("\(error)\n",stderr);exit(1)}
