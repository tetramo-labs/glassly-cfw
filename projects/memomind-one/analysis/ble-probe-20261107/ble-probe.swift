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
try need(CommandLine.arguments.count==3 || CommandLine.arguments.count==4,"Usage: ble-probe register|adv|status|notify|resume NEW_CAPTURE_DIRECTORY [slot]")
let mode=CommandLine.arguments[1];try need(["register","adv","status","notify","resume"].contains(mode),"Unknown op: register|adv|status|notify|resume")
let output=URL(fileURLWithPath:CommandLine.arguments[2],isDirectory:true)
try need(mkdir(output.path,0o700)==0,"Output must be new")
let fd=open(output.appendingPathComponent("trace.jsonl").path,O_WRONLY|O_CREAT|O_EXCL,0o600)
try need(fd>=0,"Trace create failed");let trace=FileHandle(fileDescriptor:fd,closeOnDealloc:true)
func record(_ event:String,_ fields:[String:Any]=[:])throws {var r=fields;r["event"]=event;r["uptime"]=ProcessInfo.processInfo.systemUptime;r["utc"]=ISO8601DateFormatter().string(from:Date());var b=try JSONSerialization.data(withJSONObject:r,options:.sortedKeys);b.append(10);try trace.write(contentsOf:b);try trace.synchronize()}
func save(_ name:String,_ value:Any)throws {try JSONSerialization.data(withJSONObject:value,options:[.prettyPrinted,.sortedKeys]).write(to:output.appendingPathComponent(name),options:.withoutOverwriting)}
let io=MacRFCOMMTransport(traffic:{e in try record(e.kind.rawValue,["hex":hex(e.data),"status":e.status as Any? ?? NSNull()])})
var result:[String:Any]=["stage":mode,"complete":false]
do {
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

 func probe(_ bytes:Data)throws->[String:Any] {
  event=event==255 ? 1:event+1
  let r=try session.request(event:event,service:15,command:0x74,body:GMTLV(kind:1,value:bytes).encoded())
  let o=try object(r);try record("ble-probe",["request":hex(bytes),"reply":o]);return o
 }
 func decode(_ o:[String:Any])throws->[String:Any] {
  let b=try unhex(o["stateHex"] as? String ?? "");try need((b.count==64 || b.count==128) && b[0]==0x42 && b[1]==0x50,"Bad probe state")
  func u16(_ i:Int)->Int{Int(b[i])|Int(b[i+1])<<8};func u32(_ i:Int)->Int{u16(i)|u16(i+2)<<16}
  return ["result":o["result"] ?? "","service":b[3],"chara":b[4],"registering":b[5],"pending":b[6],"advSlots":b[7],
          "serviceHandle":u16(8),"valueHandle":u16(10),"cccdHandle":u16(12),"props":b[18],"writes":u32(20),"notified":u32(24),
          "notifyFailed":u32(28),"lastLen":u16(32),"cccd":b[34],"peer":hex(b[36..<42]),"last":hex(b[42..<60]),"rc":u32(60),
          "slot":b.count==128 ? hex(b[64..<120]):"","slotConfigured":b.count==128 ? Int(b[72]):-1,"slotEnabled":b.count==128 ? Int(b[73]):-1,"slotState":b.count==128 ? Int(b[75]):-1,"slotId":b.count==128 ? Int(b[77]):-1,"linkFlags":b.count==128 ? hex(b[120..<124]):""]
 }
 var reply:[String:Any]
 switch mode {
 case "register": reply=try probe(Data([0x42,0x50,1,1]))
 case "adv": reply=try probe(Data([0x42,0x50,1,2,UInt8(CommandLine.arguments.count>3 ? Int(CommandLine.arguments[3]) ?? 0:0)]))
 case "notify": reply=try probe(Data([0x42,0x50,1,4]+Array("glassly".utf8)))
 case "resume": reply=try probe(Data([0x42,0x50,1,5]))
 default: reply=try probe(Data([0x42,0x50,1,3]))
 }
 let state=try decode(reply);result["probe"]=state;result["complete"]=true
 print(String(data:try JSONSerialization.data(withJSONObject:state,options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
 try save("result.json",result);io.close()
} catch {result["error"]=String(describing:error);try? save("failure.json",result);io.close();fputs("\(error)\n",stderr);exit(1)}
