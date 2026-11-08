// Enable the notification relay (command 0x78), poll it for a while and print every
// record with the relay's connection flag, then disable it. Usage: ancs-poll SECONDS NEW_CAPTURE_DIRECTORY
import Foundation
import Darwin
import MemoMindCore
import MemoMindBluetooth
struct Failure: Error { let reason: String }
func need(_ b: Bool,_ s: String) throws { if !b { throw Failure(reason:s) } }
func hex(_ b: Data)->String { b.map{String(format:"%02x",$0)}.joined() }
try need(CommandLine.arguments.count==3,"Usage: ancs-poll SECONDS NEW_CAPTURE_DIRECTORY")
let seconds=Double(CommandLine.arguments[1]) ?? 60
let output=URL(fileURLWithPath:CommandLine.arguments[2],isDirectory:true)
try need(mkdir(output.path,0o700)==0,"Output must be new")
let fd=open(output.appendingPathComponent("trace.jsonl").path,O_WRONLY|O_CREAT|O_EXCL,0o600)
try need(fd>=0,"Trace create failed");let trace=FileHandle(fileDescriptor:fd,closeOnDealloc:true)
func record(_ event:String,_ fields:[String:Any]=[:])throws {var r=fields;r["event"]=event;r["uptime"]=ProcessInfo.processInfo.systemUptime;r["utc"]=ISO8601DateFormatter().string(from:Date());var b=try JSONSerialization.data(withJSONObject:r,options:[.sortedKeys]);b.append(10);trace.write(b)}
func save(_ name:String,_ value:Any)throws {try JSONSerialization.data(withJSONObject:value,options:[.prettyPrinted,.sortedKeys]).write(to:output.appendingPathComponent(name),options:.withoutOverwriting)}
func log(_ s:String){print(String(format:"[%.1f] ",ProcessInfo.processInfo.systemUptime)+s);fflush(stdout)}
let io=MacRFCOMMTransport(traffic:{e in try record(e.kind.rawValue,["hex":hex(e.data),"status":e.status as Any? ?? NSNull()])})
var result:[String:Any]=["complete":false,"records":[String](),"polls":0]
do {
 try io.connect(address:"4C:3C:8F:90:CC:C3",service:.normal)
 let session=GMSession(transport:io,timeout:120)
 let identity=try session.probe();try identity.validate(address:"4C:3C:8F:90:CC:C3")
 var event:UInt8=0x30
 func raw(_ m:GMMessage)throws->Data {try need(m.tlvs.count==1 && m.tlvs[0].kind==5,"JSON TLV expected");var b=m.tlvs[0].value;while b.last==0{b.removeLast()};return b}
 func object(_ m:GMMessage)throws->[String:Any] {guard let o=try JSONSerialization.jsonObject(with:raw(m)) as? [String:Any] else{throw Failure(reason:"JSON object expected")};return o}
 func request(_ command:UInt8,_ bytes:Data=Data())throws->[String:Any] {
  event=event==255 ? 1:event+1
  let r=try session.request(event:event,service:15,command:command,body:bytes.isEmpty ? Data():GMTLV(kind:1,value:bytes).encoded(),responseFilter:{m in try object(m)["result"] as? String != "settled"})
  let o=try object(r);try record("reply",["command":command,"bytesHex":hex(bytes),"value":o]);return o
 }
 let caps=try request(0x7e);try save("capabilities.json",caps)
 log("version \(caps["version"] ?? "?")")
 func relay(_ op:UInt8)throws->[String:Any]{try request(0x78,Data([0x41,0x4e,1,op]))}
 let enabled=try relay(1);try need(enabled["active"] as? Int==1,"Relay enable refused: \(enabled)")
 log("relay enabled: connected=\(enabled["connected"] ?? "?") session=\(enabled["session"] ?? "?") generation=\(enabled["generation"] ?? "?")")
 var records=[String]();var polls=0;let deadline=Date().addingTimeInterval(seconds);var lastRenew=Date()
 while Date()<deadline {
  Thread.sleep(forTimeInterval:2)
  let renew=Date().timeIntervalSince(lastRenew)>40
  let r=try relay(renew ? 5:3);if renew {lastRenew=Date()}
  polls+=1
  let got=(r["records"] as? [String]) ?? []
  for rec in got {records.append(rec);log("record \(rec)")}
  if polls%5==1 || !got.isEmpty {log("poll \(polls): connected=\(r["connected"] ?? "?") active=\(r["active"] ?? "?") rejected=\(r["rejected"] ?? "?") drops=\(r["drops"] ?? "?") session=\(r["session"] ?? "?")")}
 }
 let disabled=try relay(2);log("relay disabled: active=\(disabled["active"] ?? "?")")
 result["records"]=records;result["polls"]=polls;result["complete"]=true
 try save("result.json",result)
 log("COMPLETE \(records.count) records over \(polls) polls")
} catch {
 result["error"]=String(describing:error);try? save("failure.json",result);log("FAILED \(error)");exit(1)
}
