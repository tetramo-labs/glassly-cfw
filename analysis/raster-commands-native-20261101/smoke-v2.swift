import Foundation
import CryptoKit
import Darwin
import MemoMindCore
import MemoMindBluetooth
struct Failure:Error{let reason:String}
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
 let image=try Data(contentsOf:URL(fileURLWithPath:"captures/firmware/raster-commands-001/firmware.bin"))
 _=try EligibleFirmware.load(data:image,expectedSHA256:"b89a6adab63bb8e09c2b05a261af4ae9b80f5b7fc4e81c15c016dc457dfba261")
 let expected=try Data(contentsOf:URL(fileURLWithPath:"captures/firmware/raster-commands-001/expected-app-header.bin"))
 try need(expected.count==256 && sha(expected)=="6a82b165c2b839a3a8f4b235074a78d0dc118388acb5a169d647fa4f05046ca8","Candidate header pin mismatch")
 try transport.connect(address:"4C:3C:8F:90:CC:C3",service:.normal)
 let session=GMSession(transport:transport);let device=try session.probe();try device.validate(address:"4C:3C:8F:90:CC:C3")
 var event:UInt8=0x30
 func jsonRequest(_ command:UInt8,_ bytes:Data=Data())throws->Data{
  event=event==255 ? 1:event+1
  let message=try session.request(event:event,service:15,command:command,body:bytes.isEmpty ? Data():GMTLV(kind:1,value:bytes).encoded())
  try need(message.tlvs.count==1 && message.tlvs[0].kind==5 && message.tlvs[0].value.count<=1024,"Expected bounded JSON response")
  var raw=message.tlvs[0].value;if raw.last==0{raw.removeLast()};return raw
 }
 let header=try jsonRequest(0x7b,Data([1,0,0,0xb0,0x1e,0,0,1]))
 let exactHeader="{\"glassly\":\"flash-read\",\"abi\":1,\"result\":\"ok\",\"device\":0,\"offset\":2011136,\"length\":256,\"hex\":\""+expected.map{String(format:"%02x",$0)}.joined()+"\"}"
 try need(header==Data(exactHeader.utf8),"Live header mismatch");try save("header-reply.json",header)
 let caps=try jsonRequest(0x7e);try save("capabilities.json",caps)
 struct Caps:Decodable{let glassly:String;let abi:Int;let profile:String;let width:Int;let height:Int;let modes:[Int];let rasterLens:String;let maxMessageBytes:Int}
 let c=try JSONDecoder().decode(Caps.self,from:caps)
 try need(c.glassly=="graphics-runtime" && c.abi==1 && c.profile=="H001Y-1.0.3.127" && c.width==600 && c.height==350 && c.modes.contains(3) && c.modes.contains(6) && c.rasterLens=="first-left" && c.maxMessageBytes==8192,"Required raster capability absent")
 func command(_ data:Data,_ wanted:String="ok")throws{
  let r=try jsonRequest(0x7d,data)
  let presentation = wanted == "ok" ? ",\"presentation\":\"scheduled\"" : ""
  let exact="{\"glassly\":\"graphics\",\"abi\":1,\"result\":\""+wanted+"\""+presentation+"}"
  try need(r==Data(exact.utf8),"Unexpected graphics reply: "+String(decoding:r,as:UTF8.self))
 }
 var frame=Data(repeating:0x22,count:105000)
 let letters=[["11110","10001","10001","11110","10100","10010","10001"],["10000","10000","10000","10000","10000","10000","11111"],["11111","10000","10000","11110","10000","10000","11111"]]
 for (letter,rows) in letters.enumerated(){for (row,line) in rows.enumerated(){for (col,b) in line.utf8.enumerated() where b==49{for dy in 0..<6{for dx in 0..<6{
  let x=100+letter*42+col*6+dx,y=100+row*6+dy,index=y*300+x/2
  frame[index]=x%2==0 ? (frame[index]&15)|0xf0 : (frame[index]&240)|15
 }}}}}
 let keyframe=try RasterCommands.fullFrame(pixels:frame);try save("keyframe-command.bin",keyframe);try save("expected-keyframe.gray4",frame)
 try command(keyframe)
 var box=Data(repeating:0,count:64*32/2)
 for y in 0..<32{for x in stride(from:0,to:64,by:2){box[y*32+x/2]=((x/8+y/8)%2==0) ? 0xff:0}}
 let delta=try RasterCommands.boundingBox(pixels:box,x:100,y:180,width:64,height:32,frameID:1)
 try save("delta-command.bin",delta);try command(delta)
 for y in 0..<32{frame.replaceSubrange((180+y)*300+50..<(180+y)*300+82,with:box[y*32..<(y+1)*32])}
 try save("expected-final.gray4",frame)
 try command(Data([3,150,0,1,1,0,0,0x8f]),"invalid")
 try command(Data([6,0,0]),"invalid")
 try record("pattern-visible",["description":"RLE letters with checkerboard below","hardwarePixelReadback":false])
 // Existing empty-geometry lease renewals hold the image while the user views it.
 let deadline=ProcessInfo.processInfo.systemUptime+90
 while ProcessInfo.processInfo.systemUptime<deadline{
  RunLoop.current.run(until:Date(timeIntervalSinceNow:0.25));try transport.checkHealth();try command(Data([36,0]))
 }
 try command(Data([11]),"cleared")
 try record("smoke-complete",["keyframeAcknowledged":true,"deltaAcknowledged":true,"invalidCommandsRejected":2,"cleared":true,"hardwarePixelReadback":false])
 transport.close();print("Keyframe/delta acknowledged; invalid commands rejected; pattern cleared. Physical visibility needs user confirmation.")
}catch{try? record("failed",["error":String(describing:error)]);transport.close();fputs("\(error)\n",stderr);exit(1)}
