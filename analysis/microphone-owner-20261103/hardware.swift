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
 let release=mode=="before" ? "record-memory-001":"microphone-owner-001"
 let expectedHash=mode=="before" ? "d65d7e3e761e4ee754e359a5921034d775267e1d0374c006e70de30cdba48f68":"0c5589c9dc9514ddedf6e9e1cc0f0b9269a8e4837712021b12fda69815e837f2"
 let imageHash=mode=="before" ? "5a6f8984773318a651f2703838672e9220615051fa36709ea591ed47e3b2e019":"e43e0f1b2745774104f84d6d406092e49d97276d37eb94831a8c0c346aaa54cb"
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
 let topology=try object(request(0x7b,Data([2]))),badmap=try object(request(0x7b,Data([3])))
 let oldTopo=try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:"captures/swift-mac-text-preflight-20261102-01/topology-before.json"))) as! NSDictionary
 let oldMap=try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:"captures/swift-mac-text-preflight-20261102-01/badmap.json"))) as! NSDictionary
 try need((topology as NSDictionary)==oldTopo && (badmap as NSDictionary)==oldMap,"Fresh topology/badmap differs from reviewed admission")
 try save("topology.json",topology);try save("badmap.json",badmap)
 result["topologyAndBadmapVerified"]=true;result["freeBeforeHex"]=caps["freeBytesHex"]
 if mode != "before" {try need(caps["version"] as? String=="GLASSLYCFW/7" && caps["displayOwner"] as? String=="minimal" && caps["storeKiB"] as? Int==256 && caps["maxMessageBytes"] as? Int==65535,"Candidate capabilities mismatch")}

 if mode=="after" {let ownership=caps["ownership"] as? [String:Any];try need(ownership?["command"] as? Int==121 && ownership?["leaseTicks"] as? Int==90000,"Ownership capability mismatch")}
 if mode=="after" {
  try need((caps["displaySettings"] as? [String:Int]) == ["position":10,"depth":11,"min":0,"max":8],"Display settings capability differs")
  let notifications=caps["notifications"] as? [String:Any]
  try need(notifications?["command"] as? Int==120 && notifications?["transport"] as? String=="poll","Notification capability differs")
  func notification(_ op:UInt8)throws->[String:Any] {try object(request(0x78,Data([65,78,1,op])))}
  let enabled=try notification(1);try need(enabled["active"] as? Int==1,"Relay enable refused")
  let polled=try notification(0);try need(polled["result"] as? String=="ok" && polled["session"] != nil,"Relay poll failed")
  let disabled=try notification(2);try need(disabled["active"] as? Int==0,"Relay disable refused")
  result["relayEnablePollDisableVerified"]=true
  let mic=try session.microphone(.status,event:&event)
  try need(!mic.active && !mic.streaming && !mic.nativeActive && !mic.pending,"Unexpected boot microphone state")
  result["microphoneIdleVerified"]=true
  func status()throws->[String:Any] {
   event=event==255 ? 1:event+1
   let r=try session.request(event:event,service:1,command:6)
   try need(r.tlvs.count==1 && r.tlvs[0].kind==2,"Status STRING expected")
   var data=r.tlvs[0].value;while data.last==0{data.removeLast()}
   let value=try JSONSerialization.jsonObject(with:data) as! [String:Any]
   try record("settings-status",value);return value
  }
  func setting(_ command:UInt8,_ value:Int)throws {
   event=event==255 ? 1:event+1
   try record("setting-request",["command":command,"value":value])
   let r=try session.request(event:event,service:1,command:command,body:GMTLV(kind:8,value:Data([UInt8(value)])).encoded())
   try need(r.tlvs == [GMTLV(kind:6,value:Data([0]))],"Setting queue refused")
  }
  func waitPosition(_ pos:Int,_ dist:Int)throws {
   let deadline=ProcessInfo.processInfo.systemUptime+3
   repeat {
    let s=try status()
    if s["pos"] as? Int==pos && s["dist"] as? Int==dist{return}
    Thread.sleep(forTimeInterval:0.1)
   } while ProcessInfo.processInfo.systemUptime<deadline
   throw Failure(reason:"Display position readback mismatch")
  }
  let original=try status()
  guard let pos=original["pos"] as? Int,let dist=original["dist"] as? Int,(0...8).contains(pos),(0...8).contains(dist) else {throw Failure(reason:"Invalid original position")}
  var restored=false
  defer {if !restored {try? setting(10,pos);try? setting(11,dist);try? record("position-restore-attempted")}}
  let newPos=pos==8 ? 7:pos+1,newDist=dist==8 ? 7:dist+1
  try setting(10,newPos);try setting(11,newDist);try waitPosition(newPos,newDist)
  result["positionChangeReadbackVerified"]=true
  try setting(10,pos);try setting(11,dist);try waitPosition(pos,dist);restored=true
  result["positionRestoreVerified"]=true
  result["originalPosition"]=["pos":pos,"dist":dist]
 }
 if mode=="after" {
  let capability=caps["recordTransport"] as? [String:Int]
  try need(capability == ["mode":126,"version":1,"maxPacketBytes":128,"maxRecordBytes":65535,"replyCapacity":64,"endpoint":1,"leaseTicks":30000],"Record capability differs")
  _=try request(0x7d,Data([11]))
  try need(session.ownership(.acquireWake,event:&event).wakeLease,"Wake refused")
  try need(session.ownership(.acquireFrame,event:&event).frameLease,"Frame refused")
  let records=try GraphicsRecordSession(session:session)
  func compressed(_ body:Data)throws->Data? {
   let reply=try records.send(body,event:&event)
   try record("compressed-command",["mode":body[0],"decodedBytes":body.count,"replyHex":reply.map(hex) as Any? ?? NSNull()])
   return reply
  }
  _=try compressed(RasterCommands.fullFrame(pixels:Data(repeating:0,count:105000)))
  _=try compressed(RasterCommands.builtinText(bytes:Data("GLASSLYCFW/7".utf8),x:20,y:30))
  _=try compressed(RasterCommands.builtinText(bytes:Data("COMPRESSED / 65535".utf8),x:20,y:80))
  let dictionary=Data([8,0])+Data((0..<4094).map{UInt8(truncatingIfNeeded:$0*37)})
  _=try compressed(dictionary);_=try compressed(dictionary)
  _=try compressed(Data([8,0])+Data(repeating:120,count:65533))
  let diagnostics=try compressed(Data([7,1]));try need(diagnostics?.count==20,"Diagnostic data reply differs")
  try need(session.ownership(.status,event:&event).framePresented,"Compressed frame not presented")
  try need(caps["modeHighBit"] as? Bool==true,"High-bit capability missing")
  _=try compressed(Data([164,0]))
  let aliasState=try compressed(Data([168])+Data(repeating:0,count:8))
  try need(aliasState?.first==40 && (aliasState?.count ?? 0)>=10,"High-bit STATE reply differs")
  result["highBitCommandsAccepted"]=true
  result["compressedCommandsAccepted"]=true;result["maximumDecodedRecordAccepted"]=65535
  result["dictionaryReuseAccepted"]=true;result["binaryReplyBytes"]=20
  try save("compressed-checkpoint.json",result)
  // Closing the owner from inside the active record must defer decoder disposal.
  _=try compressed(Data([11]));result["recordCleanupAccepted"]=true
  let after=try object(request(0x7e));result["freeAfterCleanupHex"]=after["freeBytesHex"]
  _=try session.ownership(.releaseFrame,event:&event);_=try session.ownership(.releaseWake,event:&event)
  try need(session.ownership(.acquireWake,event:&event).wakeLease,"Visual wake refused")
  try need(session.ownership(.acquireFrame,event:&event).frameLease,"Visual frame refused")
  let visual=try GraphicsRecordSession(session:session)
  _=try visual.send(RasterCommands.fullFrame(pixels:Data(repeating:0,count:105000)),event:&event)
  _=try visual.send(RasterCommands.builtinText(bytes:Data("GLASSLYCFW/7".utf8),x:20,y:30),event:&event)
  _=try visual.send(RasterCommands.builtinText(bytes:Data("COMPRESSED / 65535".utf8),x:20,y:80),event:&event)
  try need(session.ownership(.status,event:&event).framePresented,"Visual frame not presented")
  result["visualLeasePendingExpiry"]=true
  print("COMPRESSED DISPLAY READY: GLASSLYCFW/7; COMPRESSED / 65535");fflush(stdout)
 }
 result["complete"]=true;try save("result.json",result);try record("complete",result);io.close();print("COMPLETE \(mode)")
} catch {result["error"]=String(describing:error);try? save("failure.json",result);try? record("failed",result);io.close();fputs("\(error)\n",stderr);exit(1)}
