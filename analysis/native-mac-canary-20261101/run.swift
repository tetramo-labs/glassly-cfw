import Foundation
import CryptoKit
import Darwin
import MemoMindCore
import MemoMindBluetooth
struct Failure:Error {let reason:String}
func need(_ value:Bool,_ reason:String)throws{if !value{throw Failure(reason:reason)}}
func sha(_ data:Data)->String{SHA256.hash(data:data).map{String(format:"%02x",$0)}.joined()}
func document(_ path:String)throws->[String:Any]{try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:path))) as! [String:Any]}
try need(CommandLine.arguments.count==3 && CommandLine.arguments[2]=="--run-fixed-canary","Explicit fixed operation required")
let output=URL(fileURLWithPath:CommandLine.arguments[1],isDirectory:true)
try need(mkdir(output.path,0o700)==0,"Output must be a new directory")
let fd=open(output.appendingPathComponent("trace.jsonl").path,O_WRONLY|O_CREAT|O_EXCL,0o600)
try need(fd>=0,"Cannot create trace")
let trace=FileHandle(fileDescriptor:fd,closeOnDealloc:true)
func record(_ event:String,_ fields:[String:Any]=[:])throws{
 var row=fields;row["event"]=event;row["utc"]=ISO8601DateFormatter().string(from:Date())
 var raw=try JSONSerialization.data(withJSONObject:row,options:.sortedKeys);raw.append(10)
 try trace.write(contentsOf:raw);try trace.synchronize()
}
func save<T:Encodable>(_ name:String,_ value:T)throws{
 let encoder=JSONEncoder();encoder.outputFormatting=[.sortedKeys,.prettyPrinted]
 try encoder.encode(value).write(to:output.appendingPathComponent(name),options:.withoutOverwriting)
}
let transport=MacRFCOMMTransport(traffic:{e in try record(e.kind.rawValue,["hex":e.data.map{String(format:"%02x",$0)}.joined(),"status":e.status as Any? ?? NSNull()])})
var attempted=false
do{
 let backup=try document("analysis/native-mac-backup-20261101/verification.json")
 try need(backup["complete"] as? Bool == true && backup["bytes"] as? Int == 3145728 && backup["all_ff"] as? Bool == true,"Complete current backup required")
 let backedUp=try Data(contentsOf:URL(fileURLWithPath:"captures/swift-mac-full-backup-20261101-01/managed-store.bin"))
 try need(backedUp.count==3145728 && sha(backedUp)==backup["sha256"] as? String,"Backup bytes changed")
 let preflight=try document("analysis/native-mac-canary-20261101/preflight-verification.json")
 try need(preflight["complete"] as? Bool == true && preflight["app_header_full256_matches"] as? Bool == true && preflight["target_and_neighbor_all_ff"] as? Bool == true && preflight["topology_and_badmap_match_backup"] as? Bool == true,"Fresh canary preflight required")
 let image=try Data(contentsOf:URL(fileURLWithPath:"captures/firmware/flash-canary-001/firmware.bin"))
 _ = try EligibleFirmware.load(data:image,expectedSHA256:"79a4158c5d82b97c248d0dd2b7e366df03206393c1c2a7275677b8985d81398a")
 let expected=try Data(contentsOf:URL(fileURLWithPath:"captures/firmware/flash-canary-001/expected-app-header.bin"))
 try need(expected.count==256 && sha(expected)=="516c270a7eff42b70744cf26bc68bb1e4568eefab4b371fb85884b08cb6727d8","Expected canary header pin")
 try transport.connect(address:"4C:3C:8F:90:CC:C3",service:.normal)
 let session=GMSession(transport:transport)
 let device=try session.probe();try device.validate(address:"4C:3C:8F:90:CC:C3");try save("device.json",device)
 let header=try session.request(event:0x92,service:15,command:0x7b,body:GMTLV(kind:1,value:Data([1,0,0,0xb0,0x1e,0,0,1])).encoded())
 try need(header.tlvs.count==1 && header.tlvs[0].kind==5 && header.tlvs[0].value.count<=768,"Bounded header response required")
 struct Header:Decodable{let glassly:String;let abi:Int;let result:String;let device:Int;let offset:Int;let length:Int;let hex:String}
 var raw=header.tlvs[0].value;if raw.last==0{raw.removeLast()}
 let exactHeader="{\"glassly\":\"flash-read\",\"abi\":1,\"result\":\"ok\",\"device\":0,\"offset\":2011136,\"length\":256,\"hex\":\""+expected.map{String(format:"%02x",$0)}.joined()+"\"}"
 try need(raw==Data(exactHeader.utf8),"Header JSON differs from fixed native serializer")
 let h=try JSONDecoder().decode(Header.self,from:raw)
 try need(h.glassly=="flash-read" && h.abi==1 && h.result=="ok" && h.device==0 && h.offset==0x1eb000 && h.length==256 && h.hex==expected.map{String(format:"%02x",$0)}.joined(),"Live canary header mismatch")
 try raw.write(to:output.appendingPathComponent("header-reply.json"),options:.withoutOverwriting)
 let client=try FixedCanaryClient(transport:transport)
 try save("profile.json",client.verifyProfile())
 let initial=try client.status();try save("initial-status.json",initial)
 try need(initial.state == .idle,"Canary boot attempt already consumed")
 try record("fixed-canary-start-intent",["device":1,"offset":0x7ff000,"neighbor":0x7fe000,"sectorBytes":4096,"operation":2,"automaticRetries":0])
 attempted=true
 var status=try client.runFixedCanary();try save("start-status.json",status)
 let deadline=ProcessInfo.processInfo.systemUptime+60
 var polls=0
 while status.state != .passed && status.state != .failed {
  try need(ProcessInfo.processInfo.systemUptime<deadline,"Observation deadline; native worker may still be running; do not repeat start")
  RunLoop.current.run(until:Date(timeIntervalSinceNow:1))
  try transport.checkHealth()
  status=try client.status();polls+=1;try save(String(format:"poll-%03d.json",polls),status)
 }
 try save("terminal-status.json",status)
 try need(status.state == .passed && status.operation==2 && status.restored && status.neighborVerified,"Fixed canary failed; no automatic recovery")
 try record("fixed-canary-passed",["operation":2,"polls":polls,"restored":status.restored,"neighborVerified":status.neighborVerified])
 print("Fixed canary passed; device reports restored target and unchanged neighbor. Independent readback still required.")
 transport.close()
}catch{
 try? record("failed",["error":String(describing:error),"startAttempted":attempted,"automaticRetry":false,"nativeWorkerMayContinue":attempted])
 transport.close();fputs("\(error)\n",stderr);exit(1)
}
