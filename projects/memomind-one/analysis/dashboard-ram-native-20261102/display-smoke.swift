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
 let image=try Data(contentsOf:URL(fileURLWithPath:"captures/firmware/dashboard-ram-002/firmware.bin"))
 try need(image.count==2230671,"Image size mismatch")
 _=try EligibleFirmware.load(data:image,expectedSHA256:"f56376fde20515c0ad2a421eb352f774b4c21f274cda2d38f012a0d008c6d14a")
 let runtime=try Data(contentsOf:URL(fileURLWithPath:"runtime/build/diagnostic-commands-001/graphics.bin"))
 try need(runtime.count==65456 && sha(runtime)=="c1d8a1ffdd4f2799de4149d2e113527b29716886f6530549e56f68f61333d3b3","Runtime pin mismatch")
 let expected=try Data(contentsOf:URL(fileURLWithPath:"captures/firmware/dashboard-ram-002/expected-app-header.bin"))
 try need(expected.count==256 && sha(expected)=="c7bd3f186f0d37277aa126c843a72a220886845e055013cfe547a1695601625a","Candidate header pin mismatch")
 try transport.connect(address:"4C:3C:8F:90:CC:C3",service:.normal)
 var notificationError:String?=nil
 let checked=CheckedIO(transport){try need(notificationError==nil,notificationError ?? "Notification failure")}
 let session=GMSession(transport:checked)
 let device=try session.probe();try device.validate(address:"4C:3C:8F:90:CC:C3");try need(device.firmwareVersion=="1.0.3.127","Expected installed firmware");try save("device.json",JSONEncoder().encode(device))
 session.unsolicited={message in do{
  try need(message.service != 15,"Unexpected reserved-service reply")
  try record("native-service-notification",["eventID":message.event,"service":message.service,"command":message.command,"bodyHex":message.body.map{String(format:"%02x",$0)}.joined()])
 }catch{notificationError=String(describing:error)}}
 var event:UInt8=0x30
 func request(_ command:UInt8,_ data:Data=Data())throws->GMMessage{
  try need(notificationError==nil,notificationError ?? "Notification failure")
  event=event==255 ? 1:event+1
  let message=try session.request(event:event,service:15,command:command,body:data.isEmpty ? Data():GMTLV(kind:1,value:data).encoded(),responseFilter:{_ in true})
  try need(notificationError==nil,notificationError ?? "Notification failure")
  return message
 }
 func raw(_ message:GMMessage)throws->Data{
  try need(message.tlvs.count==1 && message.tlvs[0].kind==5 && message.tlvs[0].value.count<=1024,"JSON TLV bound")
  var data=message.tlvs[0].value;if data.last==0{data.removeLast()};return data
 }
 func exact(_ message:GMMessage,_ wanted:String)throws{try need(raw(message)==Data(wanted.utf8),"Unexpected reply")}
 let header=try raw(request(0x7b,Data([1,0,0,0xb0,0x1e,0,0,1])))
 let exactHeader="{\"glassly\":\"flash-read\",\"abi\":1,\"result\":\"ok\",\"device\":0,\"offset\":2011136,\"length\":256,\"hex\":\""+expected.map{String(format:"%02x",$0)}.joined()+"\"}"
 try need(header==Data(exactHeader.utf8),"Live header mismatch");try save("header-reply.json",header)
 var samples:[[String:Any]]=[]
 try record("measurement-intent",["samples":10,"intervalSeconds":0.5,"displayCommands":0,"otaCommands":0,"flashMutations":0,"largestBlockSupported":false,"temporaryAllocationCaveat":"Probe allocates its JSON template before sampling; values include that transient allocation and connection traffic. Low-water is a sum of per-pool minima, not largest block or an atomic pair."])
 for index in 0..<10 {
 let caps=try raw(request(0x7e));try save(String(format:"capabilities-%02d.json",index),caps)
 struct Caps:Decodable{let glassly:String;let abi:Int;let profile:String;let width:Int;let height:Int;let modes:[Int];let diagnostics:String;let snapshotBytes:Int;let cleanup:String;let maxMessageBytes:Int;let storeKiB:Int;let textMaxBytes:Int;let textFont:String;let missingGlyph:String;let emptyGeometry:String;let bundleModes:[Int];let freeBytesHex:String;let lowWaterBytesHex:String}
 let c=try JSONDecoder().decode(Caps.self,from:caps)
 try need(c.glassly=="graphics-runtime" && c.abi==1 && c.profile=="H001Y-1.0.3.127" && c.width==600 && c.height==350 && c.modes==[3,6,7,8,9,11,15,19,20,36,37,38,39,40,41] && c.diagnostics=="native-v1" && c.snapshotBytes==20 && c.cleanup=="graphics-input-current-screen" && c.maxMessageBytes==8192 && c.storeKiB==64 && c.textMaxBytes==255 && c.textFont=="native-resource" && c.missingGlyph=="reject" && c.emptyGeometry=="lease-only" && c.bundleModes==[3,6,9,15,19,20,36,37,38,39,40,41],"Required diagnostics capabilities absent")
 // Exact native canonical capabilities reject duplicate/escaped-key ambiguity.
 for h in [c.freeBytesHex,c.lowWaterBytesHex]{try need(h.utf8.count==8 && h.utf8.allSatisfy{48...57 ~= $0 || 97...102 ~= $0},"Heap snapshot syntax")}
 let exactCaps="{\"glassly\":\"graphics-runtime\",\"abi\":1,\"profile\":\"H001Y-1.0.3.127\",\"width\":600,\"height\":350,\"flashRead\":123,\"inputObserver\":{\"command\":124,\"capacity\":32,\"leaseTicks\":30000},\"modes\":[3,6,7,8,9,11,15,19,20,36,37,38,39,40,41],\"diagnostics\":\"native-v1\",\"snapshotBytes\":20,\"cleanup\":\"graphics-input-current-screen\",\"rasterLens\":\"first-left\",\"bundleModes\":[3,6,9,15,19,20,36,37,38,39,40,41],\"bundleMaxSegments\":255,\"textMaxBytes\":255,\"textFont\":\"native-resource\",\"missingGlyph\":\"reject\",\"maxMessageBytes\":8192,\"storeKiB\":64,\"builtinText\":true,\"emptyGeometry\":\"lease-only\",\"maxGeometryRecords\":255,\"leaseTicks\":1000,\"tickMs\":1,\"flashCanary\":122,\"registryBytes\":256,\"writableStaticBytes\":256,\"freeBytesHex\":\"\(c.freeBytesHex)\",\"lowWaterBytesHex\":\"\(c.lowWaterBytesHex)\"}"
 try need(caps==Data(exactCaps.utf8),"Unexpected capabilities schema")
  guard let free=UInt32(c.freeBytesHex,radix:16),let low=UInt32(c.lowWaterBytesHex,radix:16) else {throw Failure(reason:"Invalid heap hexadecimal value")}
  let sample:[String:Any]=["index":index,"uptime":ProcessInfo.processInfo.systemUptime,"eventID":event,"freeBytes":free,"lowWaterBytes":low,"freeBytesHex":c.freeBytesHex,"lowWaterBytesHex":c.lowWaterBytesHex]
  samples.append(sample);try record("heap-sample",sample)
  if index != 9 {RunLoop.current.run(until:Date().addingTimeInterval(0.5))}
 }
 try need(notificationError==nil,notificationError ?? "Notification failure")
 let frees=samples.map{($0["freeBytes"] as! UInt32)}
 let lows=samples.map{($0["lowWaterBytes"] as! UInt32)}
 let result:[String:Any]=["complete":true,"samples":samples,"sampleCount":samples.count,"minimumFreeBytes":frees.min()!,"maximumFreeBytes":frees.max()!,"minimumLowWaterBytes":lows.min()!,"maximumLowWaterBytes":lows.max()!,"runtimeRelease":"dashboard-ram-002","appHeaderSHA256":sha(expected),"flashMutations":0,"displayCommands":0,"otaCommands":0,"automaticRetries":0,"largestBlockSupported":false,"telemetryIncludesTemporaryProbeAllocation":true,"requestedPauseSeconds":0.5,"serviceDiscovery":transport.serviceDiscoverySource as Any? ?? NSNull()]
 try save("result.json",JSONSerialization.data(withJSONObject:result,options:[.prettyPrinted,.sortedKeys]))
 try record("measurement-complete",["sampleCount":samples.count,"minimumFreeBytes":frees.min()!,"maximumFreeBytes":frees.max()!])
 // The preceding result.json describes the read-only measurement phase.
 func graphics(_ data:Data,_ result:String="ok")throws{
  let suffix=result=="ok" ? ",\"presentation\":\"scheduled\"":""
  try exact(request(0x7d,data),"{\"glassly\":\"graphics\",\"abi\":1,\"result\":\""+result+"\""+suffix+"}")
 }
 try record("display-smoke-start",["readOnlyPhaseComplete":true])
 try graphics(RasterCommands.cleanupSession(),"cleared")
 try graphics(RasterCommands.fullFrame(pixels:Data(repeating:0,count:105000)))
 try graphics(RasterCommands.builtinText("RAM",x:100,y:120,options:31))
 try record("pattern-visible",["text":"RAM","background":"black","holdSeconds":90,"physicalOutputConfirmed":false])
 let until=ProcessInfo.processInfo.systemUptime+90
 var renewals=0
 while ProcessInfo.processInfo.systemUptime<until {
  RunLoop.current.run(until:Date().addingTimeInterval(0.25))
  try graphics(Data([36,0]));renewals+=1
 }
 try graphics(RasterCommands.cleanupSession(),"cleared")
 RunLoop.current.run(until:Date().addingTimeInterval(0.5))
 let after=try raw(request(0x7e));try save("capabilities-after-display.json",after)
 try save("display-smoke-result.json",JSONSerialization.data(withJSONObject:["commandsAccepted":true,"cleared":true,"leaseRenewals":renewals,"physicalOutputConfirmed":false],options:[.prettyPrinted,.sortedKeys]))
 try record("display-smoke-complete",["leaseRenewals":renewals,"cleared":true])
 transport.close()
 print(String(decoding:try JSONSerialization.data(withJSONObject:result,options:[.prettyPrinted,.sortedKeys]),as:UTF8.self))
}catch{try? record("failed",["error":String(describing:error)]);transport.close();fputs("\(error)\n",stderr);exit(1)}
