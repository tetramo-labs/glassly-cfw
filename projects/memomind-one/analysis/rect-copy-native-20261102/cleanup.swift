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
 try command(Data([11]),"cleared")
 try record("cleanup-complete",["clearAcknowledged":true,"hardwarePixelReadback":false])
 transport.close();print("Clear acknowledged after exact image header check")
}catch{try? record("failed",["error":String(describing:error)]);transport.close();fputs("\(error)\n",stderr);exit(1)}
