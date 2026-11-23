import Foundation
import CryptoKit
import Darwin
import MemoMindCore
import MemoMindBluetooth
struct VerificationError: Error { let reason: String }
func need(_ ok: Bool, _ reason: String) throws { if !ok { throw VerificationError(reason:reason) } }
func sha(_ data:Data)->String { SHA256.hash(data:data).map{String(format:"%02x",$0)}.joined() }
let output=URL(fileURLWithPath:CommandLine.arguments[1],isDirectory:true)
try need(mkdir(output.path,0o700)==0,"Output must be a new directory")
let fd=open(output.appendingPathComponent("trace.jsonl").path,O_WRONLY|O_CREAT|O_EXCL,0o600)
try need(fd>=0,"Cannot create trace")
let trace=FileHandle(fileDescriptor:fd,closeOnDealloc:true)
func record(_ event:String,_ fields:[String:Any]=[:]) throws {
 var row=fields;row["event"]=event;row["utc"]=ISO8601DateFormatter().string(from:Date())
 var raw=try JSONSerialization.data(withJSONObject:row,options:.sortedKeys);raw.append(10)
 try trace.write(contentsOf:raw);try trace.synchronize()
}
func save(_ name:String,_ data:Data)throws {try data.write(to:output.appendingPathComponent(name),options:.withoutOverwriting)}
func json<T:Encodable>(_ value:T)throws->Data{let e=JSONEncoder();e.outputFormatting=[.prettyPrinted,.sortedKeys];return try e.encode(value)}
struct Region:Decodable,Equatable{let device:Int;let start:Int;let end:Int}
struct Profile:Decodable{let glassly:String;let abi:Int;let result:String;let profile:String;let maxRead:Int;let alignment:Int;let ranges:[Region]}
struct Header:Decodable{let glassly:String;let abi:Int;let result:String;let device:Int;let offset:Int;let length:Int;let hex:String}
let transport=MacRFCOMMTransport(traffic:{e in try record(e.kind.rawValue,["hex":e.data.map{String(format:"%02x",$0)}.joined(),"status":e.status as Any? ?? NSNull()])})
do {
 let expected=try Data(contentsOf:URL(fileURLWithPath:"captures/firmware/exclusive-store-reader-001/expected-app-header.bin"))
 try need(expected.count==256 && sha(expected)=="117219ae77258054a768244fac70014ad96c77f88ed3ee116dce45ec32aa6167","Expected header pin mismatch")
 try transport.connect(address:"4C:3C:8F:90:CC:C3",service:.normal)
 let session=GMSession(transport:transport)
 let device=try session.probe();try device.validate(address:"4C:3C:8F:90:CC:C3")
 try save("device.json",json(device))
 func request(_ event:UInt8,_ bytes:[UInt8])throws->Data{
  let message=try session.request(event:event,service:15,command:0x7b,body:GMTLV(kind:1,value:Data(bytes)).encoded())
  try need(message.tlvs.count==1 && message.tlvs[0].kind==5 && message.tlvs[0].value.count<=768,"Expected one bounded JSON TLV")
  var raw=message.tlvs[0].value;if raw.last==0{raw.removeLast()};return raw
 }
 let query=try request(0x91,[0]);try save("profile.json",query)
 let p=try JSONDecoder().decode(Profile.self,from:query)
 let ranges=[Region(device:0,start:0,end:65536),Region(device:0,start:0x1eb000,end:0x1eb100),Region(device:0,start:0x7fc000,end:0x7fe000),Region(device:1,start:0x500000,end:0x800000)]
 try need(p.glassly=="flash-read" && p.abi==1 && p.result=="ok" && p.profile=="H001Y-1.0.3.127-full-store-read-v1" && p.maxRead==256 && p.alignment==256 && p.ranges==ranges,"Runtime profile or allowlist mismatch")
 let raw=try request(0x92,[1,0,0x00,0xb0,0x1e,0x00,0x00,0x01]);try save("header-reply.json",raw)
 let h=try JSONDecoder().decode(Header.self,from:raw)
 try need(h.glassly=="flash-read" && h.abi==1 && h.result=="ok" && h.device==0 && h.offset==0x1eb000 && h.length==256,"Read echo mismatch")
 try need(h.hex==expected.map{String(format:"%02x",$0)}.joined(),"Live app header differs from pinned candidate")
 try save("app-header.bin",expected)
 let before=try request(0x93,[2]);try save("topology-before.json",before)
 let badmap=try request(0x94,[3]);try save("badmap.json",badmap)
 let backupFD=open(output.appendingPathComponent("managed-store.bin").path,O_WRONLY|O_CREAT|O_EXCL,0o600)
 try need(backupFD>=0,"Cannot create backup")
 let backup=FileHandle(fileDescriptor:backupFD,closeOnDealloc:true)
 var sectors=Data()
 for page in 0..<12288 {
  let offset=0x500000+page*256
  let req:[UInt8]=[1,1,UInt8(truncatingIfNeeded:offset),UInt8(truncatingIfNeeded:offset>>8),UInt8(truncatingIfNeeded:offset>>16),0,0,1]
  let reply=try request(UInt8((0xa0+page)%255+1),req)
  try record("page-reply",["page":page,"json":String(decoding:reply,as:UTF8.self)])
  let pageHeader=try JSONDecoder().decode(Header.self,from:reply)
  try need(pageHeader.glassly=="flash-read" && pageHeader.abi==1 && pageHeader.result=="ok" && pageHeader.device==1 && pageHeader.offset==offset && pageHeader.length==256,"Sector page echo mismatch")
  let hex=Array(pageHeader.hex.utf8)
  try need(hex.count==512 && hex.allSatisfy{ (48...57).contains($0) || (97...102).contains($0) },"Invalid sector page hex")
  var chunk=Data()
  for i in stride(from:0,to:512,by:2) {chunk.append(UInt8(String(decoding:hex[i...i+1],as:UTF8.self),radix:16)!)}
  try backup.write(contentsOf:chunk);try backup.synchronize()
  sectors.append(chunk)
  try record("page-saved",["page":page,"offset":offset,"bytes":chunk.count,"sha256":sha(chunk)])
  if (page+1)%256==0 {fputs("Backed up \(sectors.count) / 3145728 bytes\n",stderr)}
 }
 try backup.close()
 let after=try request(0xc0,[2]);try save("topology-after.json",after)
 let result:[String:Any]=["complete":true,"transport":"native macOS RFCOMM","runtimeProfile":p.profile,"appHeaderFull256Matches":true,"appHeaderSHA256":sha(expected),"flashMutations":0,"automaticRetries":0,"backupBytes":sectors.count,"backupSHA256":sha(sectors),"backupAllFF":sectors.allSatisfy{$0==255},"diagnosticsRequireIndependentValidation":true,"serviceDiscovery":transport.serviceDiscoverySource as Any? ?? NSNull()]
 try record("verification-complete",result)
 let report=try JSONSerialization.data(withJSONObject:result,options:[.prettyPrinted,.sortedKeys]);try save("result.json",report);print(String(decoding:report,as:UTF8.self))
 transport.close()
} catch {try? record("failed",["error":String(describing:error)]);transport.close();fputs("\(error)\n",stderr);exit(1)}
