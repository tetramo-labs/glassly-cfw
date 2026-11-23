import Foundation
import CryptoKit
import Darwin
import MemoMindCore
import MemoMindBluetooth
struct Failure: Error { let reason: String }
func need(_ b: Bool,_ s: String) throws { if !b { throw Failure(reason:s) } }
func hex(_ b: Data)->String { b.map{String(format:"%02x",$0)}.joined() }
func sha(_ b: Data)->String { hex(Data(SHA256.hash(data:b))) }
func le(_ n: UInt32,_ bytes: Int)->Data { Data((0..<bytes).map{UInt8(truncatingIfNeeded:n >> ($0*8))}) }
func unhex(_ s:String)throws->Data { let a=Array(s.utf8);try need(a.count%2==0,"Odd hex");var b=Data();for i in stride(from:0,to:a.count,by:2){guard let n=UInt8(String(bytes:a[i..<i+2],encoding:.utf8)!,radix:16) else{throw Failure(reason:"Bad hex")};b.append(n)};return b }
try need(CommandLine.arguments.count==3,"Usage: hardware before|after NEW_CAPTURE_DIRECTORY")
let mode=CommandLine.arguments[1];try need(["before","after"].contains(mode),"Unknown stage")
let output=URL(fileURLWithPath:CommandLine.arguments[2],isDirectory:true)
try need(mkdir(output.path,0o700)==0,"Output must be new")
let fd=open(output.appendingPathComponent("trace.jsonl").path,O_WRONLY|O_CREAT|O_EXCL,0o600)
try need(fd>=0,"Trace create failed");let trace=FileHandle(fileDescriptor:fd,closeOnDealloc:true)
func record(_ event:String,_ fields:[String:Any]=[:])throws {var r=fields;r["event"]=event;r["uptime"]=ProcessInfo.processInfo.systemUptime;r["utc"]=ISO8601DateFormatter().string(from:Date());var b=try JSONSerialization.data(withJSONObject:r,options:.sortedKeys);b.append(10);try trace.write(contentsOf:b);try trace.synchronize()}
func save(_ name:String,_ value:Any)throws {try JSONSerialization.data(withJSONObject:value,options:[.prettyPrinted,.sortedKeys]).write(to:output.appendingPathComponent(name),options:.withoutOverwriting)}
let io=MacRFCOMMTransport(traffic:{e in try record(e.kind.rawValue,["hex":hex(e.data),"status":e.status as Any? ?? NSNull()])})
var result:[String:Any]=["stage":mode,"complete":false,"flashAssetWritesStarted":false,"physicalOutputConfirmed":false]
do {
 let release="ble-probe-003"
 let expectedHash="692401e424ecc4e492dd18394a5985f7f554caeae29c4ceafc6ae6040f6225db"
 let imageHash="80364527bd91081bb31c36fa29899d958af827d6e04d2124ab5b9dd663e3b1bb"
 let image=try Data(contentsOf:URL(fileURLWithPath:"captures/firmware/\(release)/firmware.bin"));try need(sha(image)==imageHash,"Image hash differs")
 let expected=try Data(contentsOf:URL(fileURLWithPath:"captures/firmware/\(release)/expected-app-header.bin"));try need(expected.count==256 && sha(expected)==expectedHash,"Pinned header differs")
 try io.connect(address:"4C:3C:8F:90:CC:C3",service:.normal)
 let session=GMSession(transport:io,timeout:120)
 let identity=try session.probe();try identity.validate(address:"4C:3C:8F:90:CC:C3")
 session.unsolicited={m in try? record("notification",["eventID":m.event,"service":m.service,"command":m.command,"bodyHex":hex(m.body)])}
 var event:UInt8=0x30
 func raw(_ m:GMMessage)throws->Data {try need(m.tlvs.count==1 && m.tlvs[0].kind==5,"JSON TLV expected");var b=m.tlvs[0].value;while b.last==0{b.removeLast()};return b}
 func object(_ m:GMMessage)throws->[String:Any] {guard let o=try JSONSerialization.jsonObject(with:raw(m)) as? [String:Any] else{throw Failure(reason:"JSON object expected")};return o}
 func request(_ command:UInt8,_ bytes:Data=Data())throws->GMMessage {
  event=event==255 ? 1:event+1;try record("request",["eventID":event,"command":command,"bytesHex":hex(bytes)])
  let r=try session.request(event:event,service:15,command:command,body:bytes.isEmpty ? Data():GMTLV(kind:1,value:bytes).encoded(),responseFilter:{m in try object(m)["result"] as? String != "settled"})
  try record("reply",["eventID":event,"command":command,"value":try object(r)]);return r
 }
 func read(_ device:UInt8,_ offset:UInt32,_ count:Int)throws->Data {
  let r=try object(request(0x7b,Data([1,device])+le(offset,4)+le(UInt32(count),2)))
  try need(r["result"] as? String=="ok" && r["device"] as? Int==Int(device) && r["offset"] as? Int==Int(offset) && r["length"] as? Int==count,"Read correlation mismatch")
  let b=try unhex(r["hex"] as? String ?? "");try need(b.count==count,"Read length mismatch");return b
 }
 try need(read(0,0x1eb000,256)==expected,"Installed app header mismatch")
 result["bootHeaderVerified"]=true;result["appHeaderSHA256"]=expectedHash;result["release"]=release
 try save("boot-checkpoint.json",result)
 let caps=try object(request(0x7e));try save("capabilities.json",caps)
 try need(caps["version"] as? String=="GLASSLYCFW/18","Wrong revision")
 _=try request(0x7d,Data([11]))
 try need(session.ownership(.acquireWake,event:&event).wakeLease,"Wake refused")
 try need(session.ownership(.acquireFrame,event:&event).frameLease,"Frame refused")
 let records=try GraphicsRecordSession(session:session)
 func draw()throws {
  _=try records.send(RasterCommands.fullFrame(pixels:Data(repeating:0,count:105000)),event:&event)
  _=try records.send(RasterCommands.builtinText(bytes:Data("GLASSLYCFW/18".utf8),x:20,y:30),event:&event)
  _=try records.send(RasterCommands.builtinText(bytes:Data("RAW PRESENT + BLE PROBE".utf8),x:20,y:80),event:&event)
  try need(session.ownership(.status,event:&event).framePresented,"Frame not presented")
 }
 try draw();try record("display-ready");print("DISPLAY READY FOR THIRTY SECONDS");fflush(stdout)
 let began=ProcessInfo.processInfo.systemUptime;var renewed=began
 while ProcessInfo.processInfo.systemUptime-began<30 {
  if ProcessInfo.processInfo.systemUptime-renewed>=25 {
   _=try session.ownership(.acquireWake,event:&event);_=try session.ownership(.acquireFrame,event:&event)
   try draw();renewed=ProcessInfo.processInfo.systemUptime
  }
  _=try session.ownership(.status,event:&event)
  Thread.sleep(forTimeInterval:1)
 }
 _=try records.send(Data([11]),event:&event)
 _=try session.ownership(.releaseFrame,event:&event);_=try session.ownership(.releaseWake,event:&event)
 result["cleanupVerified"]=true;result["displayHoldSeconds"]=30
 result["complete"]=true;try save("result.json",result);try record("complete",result);io.close();print("COMPLETE \(mode)")
} catch {result["error"]=String(describing:error);try? save("failure.json",result);try? record("failed",result);io.close();fputs("\(error)\n",stderr);exit(1)}
