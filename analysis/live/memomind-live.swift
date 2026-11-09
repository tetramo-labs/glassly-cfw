// Test-only MemoMind link: it keeps the glasses awake only while a test is armed.
// Loading steps opens the link; after the last step, or IDLE_EXIT_SECONDS (900) without
// input or commands, it releases the display, closes and exits so the glasses sleep.
// Long-lived MemoMind link. Holds the RFCOMM session with heartbeats, takes one
// command per line appended to $LIVE_DIR/in, and appends every event as a JSON
// line to $LIVE_DIR/out.jsonl, so results can be read while it keeps running.
// Commands:
//   open | close | quit           connect / release the Classic link (the iPhone cannot share it)
//   status | caps                 ownership status / capabilities (0x7e)
//   wake | frame | release        acquire wake, acquire frame, release frame+wake
//   cmd <hex> [bodyHex]           service 15 request, body sent as one kind-1 TLV
//   scene <hex>                   graphics record (0x7d) through the record session
//   ble <op> [arg]                GATT probe (0x74): 1 register, 2 adv, 3 status, 5 resume
//   hold <seconds>                pause command processing (heartbeats continue)
//   buttons                       observe buttons + head gestures (logged as "input")
//   steps <file.json>             load [{"label":…,"commands":[…]}]; a double-click on the glasses runs the next step
//   next                          run the next step now
import Foundation
import Darwin
import MemoMindCore
import MemoMindBluetooth
struct Failure: Error { let reason: String }
func hex(_ b: Data)->String { b.map{String(format:"%02x",$0)}.joined() }
func unhex(_ s:String)->Data? { let a=Array(s.utf8);guard a.count%2==0 else{return nil};var b=Data();for i in stride(from:0,to:a.count,by:2){guard let n=UInt8(String(bytes:a[i..<i+2],encoding:.utf8)!,radix:16) else{return nil};b.append(n)};return b }
let dir=URL(fileURLWithPath:ProcessInfo.processInfo.environment["LIVE_DIR"] ?? "/tmp/memomind-live",isDirectory:true)
let address=ProcessInfo.processInfo.environment["MEMOMIND_ADDRESS"] ?? "4C:3C:8F:90:CC:C3"
let idleExit=Double(ProcessInfo.processInfo.environment["IDLE_EXIT_SECONDS"] ?? "900") ?? 900
var lastActivity=ProcessInfo.processInfo.systemUptime
let beatSeconds=Double(ProcessInfo.processInfo.environment["HEARTBEAT_SECONDS"] ?? "5") ?? 5
try? FileManager.default.createDirectory(at:dir,withIntermediateDirectories:true)
let inPath=dir.appendingPathComponent("in").path, outPath=dir.appendingPathComponent("out.jsonl").path
if !FileManager.default.fileExists(atPath:inPath){FileManager.default.createFile(atPath:inPath,contents:nil)}
if !FileManager.default.fileExists(atPath:outPath){FileManager.default.createFile(atPath:outPath,contents:nil)}
let out=FileHandle(forWritingAtPath:outPath)!;out.seekToEndOfFile()
func emit(_ event:String,_ fields:[String:Any]=[:]){var r=fields;r["event"]=event;r["utc"]=ISO8601DateFormatter().string(from:Date());r["uptime"]=ProcessInfo.processInfo.systemUptime
 if var b=try? JSONSerialization.data(withJSONObject:r,options:.sortedKeys){b.append(10);out.write(b)}}
var inOffset=(try? FileManager.default.attributesOfItem(atPath:inPath)[.size] as? UInt64) ?? 0
func nextCommands()->[String]{
 guard let h=FileHandle(forReadingAtPath:inPath) else{return []};defer{h.closeFile()}
 h.seek(toFileOffset:inOffset);let d=h.readDataToEndOfFile()
 guard let s=String(data:d,encoding:.utf8),let cut=s.lastIndex(of:"\n") else{return []}
 let done=String(s[...cut]);inOffset+=UInt64(done.utf8.count)
 return done.split(separator:"\n").map{$0.trimmingCharacters(in:.whitespaces)}.filter{!$0.isEmpty}
}
var io:MacRFCOMMTransport?, session:GMSession?, records:GraphicsRecordSession?
var lastBeatLog=0.0, lastObserveTry=0.0
var event:UInt8=0x30, framed=false, lastBeat=0.0, lastRenew=0.0, holdUntil=0.0
var pendingOwnership:[OwnershipSnapshot]=[]
var observer:ButtonObserverClient?, lastPoll=0.0, wantButtons=false, firstPoll=true, lastStepAt=0.0
var steps:[[String:Any]]=[], stepIndex=0, finished=false, finishedAt=0.0
func object(_ m:GMMessage)->Any{guard m.tlvs.count==1,m.tlvs[0].kind==5 else{return ["bodyHex":hex(m.body)]};var b=m.tlvs[0].value;while b.last==0{b.removeLast()}
 return (try? JSONSerialization.jsonObject(with:b)) ?? ["text":String(decoding:b,as:UTF8.self)]}
func request(_ command:UInt8,_ bytes:Data=Data())throws->Any{
 guard let s=session else{throw Failure(reason:"link closed")}
 event=event==255 ? 1:event+1
 let r=try s.request(event:event,service:15,command:command,body:bytes.isEmpty ? Data():GMTLV(kind:1,value:bytes).encoded(),
   responseFilter:{m in ((object(m) as? [String:Any])?["result"] as? String) != "settled"})
 return object(r)
}
func open()throws{
 if session != nil {return}
 let t=MacRFCOMMTransport(traffic:{_ in})
 try t.connect(address:address,service:.normal)
 let s=GMSession(transport:t,timeout:20)
 let identity=try s.probe();try identity.validate(address:address)
 s.unsolicited={m in
  if m.service==15,m.command==0x79,let o=try? OwnershipSnapshot.decode(m) { pendingOwnership.append(o) }
  emit("notification",["service":m.service,"command":m.command,"bodyHex":hex(m.body)])}
 io=t;session=s;records=try GraphicsRecordSession(session:s);framed=false
 emit("opened",["firmware":identity.firmwareVersion])
 if wantButtons { do { try observe();emit("observing") } catch { emit("error",["command":"buttons (reconnect)","error":String(describing:error)]) } }
}
func observe()throws{
 guard let s=session else{throw Failure(reason:"link closed")}
 let o=ButtonObserverClient(session:s,initialEvent:0x90);_=try o.subscribe(nonce:UInt32.random(in:1...UInt32.max),mask:3);observer=o;firstPoll=true
}
func close(){
 if let o=observer{_=try? o.stop()}
 if let s=session{_=try? s.ownership(.releaseFrame,event:&event);_=try? s.ownership(.releaseWake,event:&event)}
 io?.close();io=nil;session=nil;records=nil;observer=nil;framed=false;emit("closed")
}
func run(_ line:String)throws->Bool{
 let p=line.split(separator:" ").map(String.init);let t=Date()
 func done(_ result:Any){emit("reply",["command":line,"ms":Date().timeIntervalSince(t)*1000,"result":result])}
 switch p[0] {
 case "quit": close();return false
 case "open": wantOpen=true;try open();done("ok")
 case "close": wantOpen=false;close()
 case "hold": holdUntil=ProcessInfo.processInfo.systemUptime+(Double(p.count>1 ? p[1]:"0") ?? 0);done("holding")
 case "status": guard let s=session else{throw Failure(reason:"link closed")};let o=try s.ownership(.status,event:&event);done(["wake":o.wakeLease,"frame":o.frameLease,"pending":o.pending])
 case "caps": done(try request(0x7e))
 case "wake": guard let s=session else{throw Failure(reason:"link closed")};done(["wake":try s.ownership(.acquireWake,event:&event).wakeLease])
 case "frame": guard let s=session else{throw Failure(reason:"link closed")};let f=try s.ownership(.acquireFrame,event:&event).frameLease;framed=f;lastRenew=ProcessInfo.processInfo.systemUptime;done(["frame":f])
 case "release": guard let s=session else{throw Failure(reason:"link closed")};_=try s.ownership(.releaseFrame,event:&event);_=try s.ownership(.releaseWake,event:&event);framed=false;done("released")
 case "cmd": guard p.count>=2,let c=unhex(p[1]),c.count==1 else{throw Failure(reason:"cmd <hex> [bodyHex]")};done(try request(c[0],p.count>2 ? (unhex(p[2]) ?? Data()):Data()))
 case "scene": guard p.count==2,let d=unhex(p[1]),let s=session else{throw Failure(reason:"scene <hex> needs an open link")}
  if records==nil {records=try GraphicsRecordSession(session:s)}
  do { let reply=try records!.send(d,event:&event) ?? Data()
   // Cache replies: [mode][request:u16][status]; 0 applied, 1 stale, 2 missing, 3 capacity, 4 refused.
   if reply.count>=4, reply[3] != 0, reply[3] != 5 { emit("scene-refused",["command":String(line.prefix(40)),"status":reply[3],"replyHex":hex(reply)]) }
   done(["replyHex":hex(reply)])
  } catch { records=nil; throw error }
 case "buttons": wantButtons=true;try observe();done("observing")
 case "steps": wantOpen=true;wantButtons=true;if session==nil{try? open()}
  guard p.count==2,let d=FileManager.default.contents(atPath:p[1]),let a=try JSONSerialization.jsonObject(with:d) as? [[String:Any]] else{throw Failure(reason:"steps <file.json>")}
  steps=a;stepIndex=0;done(["steps":a.count,"next":a.first?["label"] ?? ""])
 case "next": try nextStep(trigger:"command");done(["index":stepIndex])
 case "ble": guard p.count>=2,let op=UInt8(p[1]) else{throw Failure(reason:"ble <op> [arg]")};var b=Data([0x42,0x50,1,op]);if p.count>2,let a=UInt8(p[2]){b.append(a)};done(try request(0x74,b))
 default: throw Failure(reason:"unknown command")
 }
 return true
}
func ownershipEvent(_ o:OwnershipSnapshot){
 guard let e=o.event else{return}
 lastActivity=ProcessInfo.processInfo.systemUptime
 emit("input",["class":"ownership","action":"\(e)","nonce":o.nonce])
 // While the CFW owns the display a double-tap arrives as an ownership "wake" event: claim it
 // (so the stock wake does not take the screen), draw the step, then report ready, like the app.
 if e == .wake, let s=session {
  let claimed=(try? s.ownership(.claim,nonce:o.nonce,event:&event)).map{$0.pending && $0.nonce==o.nonce} ?? false
  emit("wake-claim",["nonce":o.nonce,"claimed":claimed])
  if ProcessInfo.processInfo.systemUptime-lastStepAt>=3 {
   lastStepAt=ProcessInfo.processInfo.systemUptime
   do { try nextStep(trigger:"double-tap (ownership)") } catch { emit("error",["step":stepIndex,"error":String(describing:error)]) }
  }
  if claimed, session != nil { _=try? s.ownership(.ready,nonce:o.nonce,event:&event) }
 }
}
func nextStep(trigger:String)throws{
 guard stepIndex<steps.count else{emit("steps-finished",["trigger":trigger]);finished=true;return}
 let step=steps[stepIndex];stepIndex+=1
 emit("step",["index":stepIndex,"of":steps.count,"label":step["label"] ?? "","trigger":trigger])
 for c in (step["commands"] as? [String]) ?? [] { _=try run(c) }
 emit("step-shown",["index":stepIndex,"label":step["label"] ?? "","next":stepIndex<steps.count ? (steps[stepIndex]["label"] ?? ""):"(end)"])
 if stepIndex>=steps.count {finished=true;finishedAt=ProcessInfo.processInfo.systemUptime}
}
emit("started",["pid":getpid(),"in":inPath,"heartbeatSeconds":beatSeconds])
signal(SIGPIPE,SIG_IGN)
var running=true
var queue:[String]=[]
var wantOpen=false, lastOpenTry=0.0
while running {
 let now=ProcessInfo.processInfo.systemUptime
 queue+=nextCommands()
 // Reconnect while a link is wanted; commands that need it wait in the queue.
 if wantOpen, session==nil, now-lastOpenTry>=10 { lastOpenTry=now; do { try open() } catch { emit("reconnect-failed",["error":String(describing:error)]) } }
 while running, !queue.isEmpty, ProcessInfo.processInfo.systemUptime>=holdUntil {
  let head=queue[0].split(separator:" ").first.map(String.init) ?? ""
  if session==nil, wantOpen, !["open","close","quit","hold","steps"].contains(head) { break }
  let line=queue.removeFirst();lastActivity=ProcessInfo.processInfo.systemUptime
  do { running=try run(line) } catch { emit("error",["command":line,"error":String(describing:error)]); if "\(error)".contains("RFCOMM") { close() } }
 }
 if running, let s=session {
  do {
   if framed, now-lastRenew>=20 { _=try request(0x7d,Data([36,0]));lastRenew=now;emit("renewed") }
   if let o=observer, now-lastPoll>=0.4 { lastPoll=now
    let snap=try o.poll()
    for r in snap.records {
     if r.classID==2 {lastActivity=ProcessInfo.processInfo.systemUptime} // buttons only; head gestures do not keep a test armed
     emit("input",["class":r.classID,"id":r.identifier,"action":r.primaryAction.map{"\($0)"} ?? r.imuGesture.map{"\($0)"} ?? "other","sequence":r.sequence])
     // A double-click advances one step; ignore the first poll's backlog and repeats within 3 s.
     if r.primaryAction == .double, !framed, !firstPoll, ProcessInfo.processInfo.systemUptime-lastStepAt>=3 {
      lastStepAt=ProcessInfo.processInfo.systemUptime
      do { try nextStep(trigger:"double-click") } catch { emit("error",["step":stepIndex,"error":String(describing:error)]) }
     }
    }
    if let last=snap.records.last { try o.acknowledge(savedThrough:last.sequence) }
    firstPoll=false
   }
   let beat=(steps.isEmpty || finished) ? beatSeconds:1.0
   if now-lastBeat>=beat { lastBeat=now;let o=try s.ownership(.status,event:&event)
    if o.event != nil { ownershipEvent(o) }
    if now-lastBeatLog>=beatSeconds { lastBeatLog=now;emit("heartbeat",["wake":o.wakeLease,"frame":o.frameLease]) } }
   while !pendingOwnership.isEmpty { ownershipEvent(pendingOwnership.removeFirst()) }
   if wantButtons, observer==nil, now-lastObserveTry>=5 { lastObserveTry=now; if (try? observe()) != nil { emit("observing") } }
  } catch { emit("link-lost",["error":String(describing:error)]);close() }
 }
 // Disarm: the last step ran, or nobody touched the test for idleExit seconds.
 // The last step stays on screen for 5 s before the display is released.
 if running, (finished && stepIndex>=steps.count && ProcessInfo.processInfo.systemUptime-finishedAt>=5) || (session != nil && ProcessInfo.processInfo.systemUptime-lastActivity>=idleExit) {
  emit("disarmed",["reason":finished ? "steps finished":"idle"]);close();running=false
 }
 usleep(100_000)
}
emit("stopped")
