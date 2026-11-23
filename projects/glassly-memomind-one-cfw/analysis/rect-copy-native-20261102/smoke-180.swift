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
 let image=try Data(contentsOf:URL(fileURLWithPath:"captures/firmware/rect-copy-001/firmware.bin"))
 _=try EligibleFirmware.load(data:image,expectedSHA256:"680163e3789831cd3eda89a60b208cb0e85eaa61c46067dbd6d59ff26cee1885")
 let expected=try Data(contentsOf:URL(fileURLWithPath:"captures/firmware/rect-copy-001/expected-app-header.bin"))
 try need(expected.count==256 && sha(expected)=="1f476db3d3a95b95bdaad72ad91dde9978c4ac411b39c32b28c438bd549597a0","Candidate header pin mismatch")
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
 try need(c.glassly=="graphics-runtime" && c.abi==1 && c.profile=="H001Y-1.0.3.127" && c.width==600 && c.height==350 && c.modes.contains(3) && c.modes.contains(6) && c.modes.contains(9) && c.rasterLens=="first-left" && c.maxMessageBytes==8192,"Required raster capability absent")
 func command(_ data:Data,_ wanted:String="ok")throws{
  let r=try jsonRequest(0x7d,data)
  let presentation = wanted == "ok" ? ",\"presentation\":\"scheduled\"" : ""
  let exact="{\"glassly\":\"graphics\",\"abi\":1,\"result\":\""+wanted+"\""+presentation+"}"
  try need(r==Data(exact.utf8),"Unexpected graphics reply: "+String(decoding:r,as:UTF8.self))
 }
 var frame=Data(repeating:0,count:105000)
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
 try save("overlap-command.bin",overlap);try command(overlap)
 frame=copyPixels(frame,100,180,101,181,63,31)
 try save("expected-overlap.gray4",frame)
 // Copy text plus updated checkerboard from odd boundaries to a separate area.
 let copied=try RasterCommands.rectangleCopy(source:RasterRectangle(x:99,y:99,width:129,height:115),destination:RasterRectangle(x:301,y:99,width:129,height:115))
 try save("copy-command.bin",copied);try command(copied)
 frame=copyPixels(frame,99,99,301,99,129,115)
 try save("expected-final.gray4",frame)
 var badBounds=copied;badBounds[1]=0x58;badBounds[2]=0x02 // x600 + nonzero width
 var badSize=copied;badSize[13]=128 // destination width differs
 try save("invalid-bounds-command.bin",badBounds);try command(badBounds,"invalid")
 try save("invalid-size-command.bin",badSize);try command(badSize,"invalid")
 try command(Data([9]),"invalid")
 try record("pattern-visible",["description":"Two RLE/checkerboard groups on black background; second group produced by mode9 copy","hardwarePixelReadback":false])
 // Existing empty-geometry lease renewals hold the image while the user views it.
 let deadline=ProcessInfo.processInfo.systemUptime+180
 while ProcessInfo.processInfo.systemUptime<deadline{
  RunLoop.current.run(until:Date(timeIntervalSinceNow:0.25));try transport.checkHealth();try command(Data([36,0]))
 }
 try command(Data([11]),"cleared")
 try record("smoke-complete",["keyframeAcknowledged":true,"deltaAcknowledged":true,"invalidCommandsRejected":3,"rectangleCopyAcknowledged":true,"overlapCopyAcknowledged":true,"cleared":true,"hardwarePixelReadback":false])
 transport.close();print("Keyframe/delta and overlap/rectangle copies acknowledged; invalid commands rejected; pattern cleared. Physical visibility needs user confirmation.")
}catch{try? record("failed",["error":String(describing:error)]);transport.close();fputs("\(error)\n",stderr);exit(1)}
