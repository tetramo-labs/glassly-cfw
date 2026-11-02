import Foundation
final class CheckedIO:MemoMindTransport {
 let base:MemoMindTransport;let check:() throws -> Void
 init(_ base:MemoMindTransport,_ check:@escaping () throws -> Void){self.base=base;self.check=check}
 func write(_ data:Data)throws{try check();try base.write(data)}
 func read(timeout:TimeInterval)throws->Data{try check();return try base.read(timeout:timeout)}
}

 func rawJSON(_ message:GMMessage)throws->Data {
  try need(message.tlvs.count==1 && message.tlvs[0].kind==5 && message.tlvs[0].value.count<=1024,"Expected bounded JSON response")
  var raw=message.tlvs[0].value;if raw.last==0{raw.removeLast()};return raw
 }

 func settledTag(_ message:GMMessage)throws->UInt16? {
  guard message.service==15 && message.command==0x7d else{return nil}
  let raw=try rawJSON(message),prefix=Data("{\"glassly\":\"scene\",\"abi\":1,\"result\":\"settled\",\"tag\":".utf8)
  guard raw.starts(with:prefix) else{return nil}
  try need(raw.last==125,"Malformed settled suffix")
  let digits=raw.dropFirst(prefix.count).dropLast()
  try need(!digits.isEmpty && digits.count<=5 && (digits.count==1 || digits.first != 48) && digits.allSatisfy{48...57 ~= $0},"Malformed settled tag")
  guard let tag=UInt16(String(decoding:digits,as:UTF8.self)) else{throw Failure(reason:"Settled tag overflow")}
  return tag
 }

 func sceneReply(_ data:Data,_ mode:UInt8,_ request:UInt16,_ epoch:UInt16?=nil)throws->UInt16 {
  let raw=try jsonRequest(0x7d,data)
  let prefix=Data("{\"glassly\":\"scene\",\"abi\":1,\"result\":\"ok\",\"replyHex\":\"".utf8),suffix=Data("\"}".utf8)
  try need(raw.starts(with:prefix) && raw.suffix(2)==suffix,"Expected exact scene reply wrapper")
  let h=Array(raw.dropFirst(prefix.count).dropLast(2));try need(h.count>=20 && h.count<=500 && h.count%2==0 && h.allSatisfy{48...57 ~= $0 || 97...102 ~= $0},"Invalid scene reply hex")
  var bytes:[UInt8]=[];for i in stride(from:0,to:h.count,by:2){bytes.append(UInt8(String(decoding:h[i...i+1],as:UTF8.self),radix:16)!)}
  let currentEpoch=UInt16(bytes[4])|UInt16(bytes[5])<<8
  try need(bytes[0]==mode && (UInt16(bytes[1])|UInt16(bytes[2])<<8)==request && bytes[3]==0 && currentEpoch>0 && (epoch==nil || epoch==currentEpoch),"Scene reply correlation/status mismatch")
  if mode==41 {try need(bytes.count==13 && bytes[11]==64 && bytes[12]==0,"RESET store size mismatch")}else{try need(bytes.count==11,"Unexpected applied reply size")}
  try need(bytes[10]==0,"Unexpected eviction count")
  try save("scene-reply-\(request).json",raw);return currentEpoch
 }
