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
try need(CommandLine.arguments.count==3,"Usage: hardware before|after|exercise NEW_CAPTURE_DIRECTORY")
let mode=CommandLine.arguments[1];try need(["before","after","exercise"].contains(mode),"Unknown stage")
let output=URL(fileURLWithPath:CommandLine.arguments[2],isDirectory:true)
try need(mkdir(output.path,0o700)==0,"Output must be new")
let fd=open(output.appendingPathComponent("trace.jsonl").path,O_WRONLY|O_CREAT|O_EXCL,0o600)
try need(fd>=0,"Trace create failed");let trace=FileHandle(fileDescriptor:fd,closeOnDealloc:true)
func record(_ event:String,_ fields:[String:Any]=[:])throws {var r=fields;r["event"]=event;r["uptime"]=ProcessInfo.processInfo.systemUptime;r["utc"]=ISO8601DateFormatter().string(from:Date());var b=try JSONSerialization.data(withJSONObject:r,options:.sortedKeys);b.append(10);try trace.write(contentsOf:b);try trace.synchronize()}
func save(_ name:String,_ value:Any)throws {try JSONSerialization.data(withJSONObject:value,options:[.prettyPrinted,.sortedKeys]).write(to:output.appendingPathComponent(name),options:.withoutOverwriting)}
let io=MacRFCOMMTransport(traffic:{e in try record(e.kind.rawValue,["hex":hex(e.data),"status":e.status as Any? ?? NSNull()])})
var result:[String:Any]=["stage":mode,"complete":false,"flashAssetWritesStarted":false,"physicalOutputConfirmed":false]
do {
 let release=mode=="before" ? "reset-undo-trim-001":"minimal-owner-flash-003"
 let expectedHash=mode=="before" ? "76d7bfc287aad7294d4d855a86d4d2cfbe8043a3b555eca41a891e17b1f7a4e6":"d4ad18483d7507826e4223d31f532bb85d5b193c92c1e69274506d04493c7603"
 let imageHash=mode=="before" ? "3bf52f5a2a6137759ddc3546c47b1ceed42a401953e75379712044d32e2206a9":"b7d8cea506a21eb909e249a62c673a3834369b9171ed29a5b7a36a37bcb8e86f"
 let image=try Data(contentsOf:URL(fileURLWithPath:"captures/firmware/\(release)/firmware.bin"));_=try EligibleFirmware.load(data:image,expectedSHA256:imageHash)
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
 if mode != "before" {try need(caps["version"] as? String=="GLASSLYCFW/1" && caps["displayOwner"] as? String=="minimal" && caps["storeKiB"] as? Int==256 && caps["maxMessageBytes"] as? Int==65535,"Candidate capabilities mismatch")}
 if mode=="exercise" {
  func graphics(_ data:Data,_ expected:String="ok")throws {try need(object(request(0x7d,data))["result"] as? String==expected,"Graphics result mismatch")}
  try graphics(Data([11]),"cleared")
  var epoch:UInt16=0
  func applied(_ response:GMMessage,mode:UInt8,id:UInt16)throws->Data {
   let o=try object(response);try need(o["glassly"] as? String=="scene" && o["result"] as? String=="ok","Scene envelope mismatch")
   let r=try unhex(o["replyHex"] as? String ?? "");try need(r.count>=10 && r[0]==mode && r[1]==UInt8(truncatingIfNeeded:id) && r[2]==UInt8(id>>8) && r[3]==0,"Scene command refused")
   let e=UInt16(r[4]) | UInt16(r[5])<<8;try need(epoch==0 || epoch==e,"Scene epoch changed");epoch=e;return r
  }
  let reset=try applied(request(0x7d,Data([41,0,0,1,0,0])),mode:41,id:1)
  try need(reset.count==13 && reset[11]==0 && reset[12]==1,"Not a256KiB scene")
  let huge=Data([8,0])+Data((0..<65533).map{UInt8(truncatingIfNeeded:$0*37)})
  let hugeReply=try session.sendLargeGraphicsMessage(huge,token:0x4d4d0001,event:&event)
  try need(object(hugeReply)["result"] as? String=="ok","Maximum raw message failed")
  result["rawMessage65535Verified"]=true;try save("large-message-checkpoint.json",result)
  var font=Data(repeating:0,count:384);font.append(contentsOf:(384..<262144).map{UInt8(truncatingIfNeeded:$0*17)})
  var count=0
  for offset in stride(from:0,to:font.count,by:65510) {
   let n=min(65510,font.count-offset),id=UInt16(count+2)
   var packet=Data([37]);packet.append(le(UInt32(epoch),2));packet.append(le(UInt32(id),2));packet.append(0)
   packet.append(le(5,4));packet.append(le(1,4));packet.append(1);packet.append(le(262144,4));packet.append(le(UInt32(offset),4));packet.append(le(UInt32(n),2))
   packet.append(font[offset..<offset+n]);result["flashAssetWritesStarted"]=true
   try record("asset-intent",["offset":offset,"bytes":n,"commandBytes":packet.count,"sha256":sha(packet)])
   let r=try session.sendLargeGraphicsMessage(packet,token:0x4d4d0100+UInt32(count),event:&event)
   _=try applied(r,mode:37,id:id);count+=1
   try record("asset-applied",["offset":offset,"bytes":n,"reply":try object(r)])
  }
  result["assetBytesAccepted"]=font.count;result["assetTransactions"]=count
  // First logical sector remains physical sector0 throughout this upload.
  var first=Data();for offset in stride(from:0,to:4096,by:256){first.append(try read(1,0x700000+UInt32(offset),256))}
  try need(first==font.prefix(4096),"Independent first-sector readback differs")
  result["independentReadbackBytes"]=4096;result["nativeWriteReadbackRequired"]=true
  try save("asset-checkpoint.json",result)
  try graphics(RasterCommands.fullFrame(pixels:Data(repeating:0,count:105000)))
  let text1=try RasterCommands.builtinText(bytes:Data("GLASSLYCFW/1".utf8),x:20,y:30)
  let text2=try RasterCommands.builtinText(bytes:Data("FLASH 256K / MSG 65535".utf8),x:20,y:80)
  try graphics(RasterCommands.bundle([text1,text2]))
  print("DISPLAY READY: GLASSLYCFW/1; FLASH 256K / MSG 65535");fflush(stdout)
  try save("display-checkpoint.json",result)
  let until=ProcessInfo.processInfo.systemUptime+180
  while ProcessInfo.processInfo.systemUptime<until {try graphics(Data([36,0]));Thread.sleep(forTimeInterval:0.25)}
  try graphics(Data([11]),"cleared");result["cleanupVerified"]=true
  result["freeAfterHex"]=try object(request(0x7e))["freeBytesHex"]
 }
 result["complete"]=true;try save("result.json",result);try record("complete",result);io.close();print("COMPLETE \(mode)")
} catch {result["error"]=String(describing:error);try? save("failure.json",result);try? record("failed",result);io.close();fputs("\(error)\n",stderr);exit(1)}
