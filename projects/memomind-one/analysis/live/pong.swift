// Interactive Pong on the MemoMind with per-element depth, run from a Mac terminal.
// Arrow keys / WASD move your paddle (the near frame); q quits. The court is seen from
// your end: the CPU paddle and the far frame sit behind the screen plane, your paddle in
// front, and the ball's disparity and size follow its distance. Every frame is one left
// and one right SHOW (flags 0x10/0x20) over command 0x7D with the moved objects inline.
import Foundation
import Darwin
import MemoMindCore
import MemoMindBluetooth
struct Failure: Error { let reason: String }
let address=ProcessInfo.processInfo.environment["MEMOMIND_ADDRESS"] ?? "4C:3C:8F:90:CC:C3"
func le16(_ v:Int)->[UInt8]{let u=UInt16(truncatingIfNeeded:max(0,v));return [UInt8(u&255),UInt8(u>>8)]}
func le32(_ v:UInt32)->[UInt8]{(0..<4).map{UInt8(truncatingIfNeeded:v>>($0*8))}}
// Terminal raw mode for single-key input.
var saved=termios();tcgetattr(0,&saved);var raw=saved;raw.c_lflag &= ~tcflag_t(ICANON|ECHO);tcsetattr(0,TCSANOW,&raw)
fcntl(0,F_SETFL,fcntl(0,F_GETFL) | O_NONBLOCK)
func restore(){tcsetattr(0,TCSANOW,&saved)}
signal(SIGINT){_ in tcsetattr(0,TCSANOW,&saved);exit(0)}
let io=MacRFCOMMTransport(traffic:{_ in})
var event:UInt8=0x30
var showMs=0.0,showCount=0
do {
 print("connecting…");try io.connect(address:address,service:.normal)
 let session=GMSession(transport:io,timeout:20)
 let identity=try session.probe();try identity.validate(address:address)
 func cmd(_ bytes:[UInt8])throws->[UInt8]{
  event=event==255 ? 1:event+1
  let r=try session.request(event:event,service:15,command:0x7D,body:GMTLV(kind:1,value:Data(bytes)).encoded(),
    responseFilter:{m in guard m.tlvs.count==1,let o=try? JSONSerialization.jsonObject(with:m.tlvs[0].value.prefix{$0 != 0}) as? [String:Any] else{return true};return (o["result"] as? String) != "settled"})
  guard r.tlvs.count==1,let o=try JSONSerialization.jsonObject(with:r.tlvs[0].value.prefix{$0 != 0}) as? [String:Any],let h=o["replyHex"] as? String else{return []}
  var b:[UInt8]=[];var i=h.startIndex;while i<h.endIndex{let j=h.index(i,offsetBy:2);b.append(UInt8(h[i..<j],radix:16)!);i=j};return b
 }
 guard try session.ownership(.acquireWake,event:&event).wakeLease, try session.ownership(.acquireFrame,event:&event).frameLease else{throw Failure(reason:"display busy: wake the glasses")}
 let epoch:UInt16=0x5151;var request:UInt16=1
 func next()->[UInt8]{request=request>=0xFFF0 ? 1:request+1;return le16(Int(request))}
 let reset=try cmd([41]+le16(Int(epoch))+next()+[0]);guard reset.count>3,reset[3]==0 else{throw Failure(reason:"reset refused \(reset)")}
 // Objects: rect record [1][id][version][3,1,color,0][x y w h][8 zero].
 var version:UInt32=1
 func rect(_ id:UInt32,_ x:Double,_ y:Double,_ w:Double,_ h:Double,_ color:UInt8=15)->[UInt8]{
  [1]+le32(id)+le32(version)+[3,1,color,0]+le16(Int(x.rounded()))+le16(Int(y.rounded()))+le16(max(2,Int(w.rounded())))+le16(max(2,Int(h.rounded())))+[UInt8](repeating:0,count:8)}
 func show(_ lens:UInt8,_ puts:[[UInt8]],_ refs:[(UInt32,UInt32)])throws{
  var b:[UInt8]=[38]+le16(Int(epoch))+next()+[0x01|lens,0,UInt8(puts.count)]
  for p in puts{b+=p};b+=le16(refs.count);for (i,v) in refs{b+=le32(i)+le32(v)}
  let t0=ProcessInfo.processInfo.systemUptime;let r=try cmd(b);showMs+=(ProcessInfo.processInfo.systemUptime-t0)*1000;showCount+=1;if r.count>3,r[3] != 0 {FileHandle.standardError.write("SHOW status \(r[3])\n".data(using:.utf8)!)}
 }
 // Court geometry: depth z 0 (far) … 1 (near).
 let cx=300.0,cy=180.0,W=230.0,H=130.0
 func scale(_ z:Double)->Double{0.35+0.65*z}
 func disparity(_ z:Double)->Double{-10+34*z}
 func project(_ X:Double,_ Y:Double,_ z:Double)->(Double,Double){(cx+X*W*scale(z),cy+Y*H*scale(z))}
 // Static frames: far (z 0) and mid (z 0.5), per eye.
 func frame(_ base:UInt32,_ z:Double,_ eye:Double)->[[UInt8]]{
  let s=scale(z),dx=eye*disparity(z)/2,x0=cx-W*s+dx,y0=cy-H*s,w=2*W*s,h=2*H*s
  return [rect(base,x0,y0,w,3,6),rect(base+1,x0,y0+h-3,w,3,6),rect(base+2,x0,y0,3,h,6),rect(base+3,x0+w-3,y0,3,h,6)]
 }
 var statics:[UInt8:[[UInt8]]]=[0x10:frame(100,0,1)+frame(110,0.5,1),0x20:frame(200,0,-1)+frame(210,0.5,-1)]
 // Seven-segment score digits (flat).
 let segs:[Character:(Double,Double,Double,Double)]=["a":(6,0,18,5),"b":(24,5,5,18),"c":(24,28,5,18),"d":(6,46,18,5),"e":(0,28,5,18),"f":(0,5,5,18),"g":(6,23,18,5)]
 let digit:[Int:String]=[0:"abcdef",1:"bc",2:"abged",3:"abgcd",4:"fgbc",5:"afgcd",6:"afgedc",7:"abc",8:"abcdefg",9:"abfgcd"]
 func score(_ base:UInt32,_ n:Int,_ x:Double)->[[UInt8]]{Array(digit[n % 10]!).enumerated().map{(i,c) in let s=segs[c]!;return rect(base+UInt32(i),x+s.0,14+s.1,s.2,s.3)}}
 var px=0.0,py=0.0,bx=0.0,by=0.0,bz=0.5,vx=0.35,vy=0.25,vz=0.55,cpx=0.0,cpy=0.0,you=0,cpu=0
 var last=ProcessInfo.processInfo.systemUptime,lastRenew=last,frames=0,fpsAt=last
 print("PONG: arrows/WASD move your paddle, q quits")
 var first=true,staticVersion:UInt32=1
 var definedScores=Set<UInt32>()
 loop: while true {
  var buf=[UInt8](repeating:0,count:16);let n=read(0,&buf,16)
  if n>0 { var i=0
   while i<n { let k=buf[i]
    if k==27,i+2<n,buf[i+1]==91 { switch buf[i+2]{case 65:py-=0.15;case 66:py+=0.15;case 67:px+=0.15;case 68:px-=0.15;default:break}; i+=3; continue }
    switch k {case 119:py-=0.15;case 115:py+=0.15;case 100:px+=0.15;case 97:px-=0.15;case 113:break loop;default:break}; i+=1 }
   px=max(-0.8,min(0.8,px));py=max(-0.8,min(0.8,py)) }
  let now=ProcessInfo.processInfo.systemUptime;let dt=min(0.2,now-last);last=now
  if now-lastRenew>=20 { _=try cmd([36,0]);lastRenew=now }
  // Physics.
  bx+=vx*dt;by+=vy*dt;bz+=vz*dt
  if abs(bx)>0.95 {vx = -vx;bx=max(-0.95,min(0.95,bx))}
  if abs(by)>0.95 {vy = -vy;by=max(-0.95,min(0.95,by))}
  cpx+=max(-0.9*dt,min(0.9*dt,bx-cpx));cpy+=max(-0.9*dt,min(0.9*dt,by-cpy))
  if bz>=1 { if abs(bx-px)<0.32 && abs(by-py)<0.3 {vz = -abs(vz)*1.04;vx+=(bx-px)*0.9;vy+=(by-py)*0.9} else {cpu+=1;bx=0;by=0;vz = -0.55;vx=0.3;vy=0.2}; bz=min(bz,1) }
  if bz<=0 { if abs(bx-cpx)<0.3 && abs(by-cpy)<0.28 {vz=abs(vz)} else {you+=1;bx=0;by=0;vz=0.55;vx = -0.3;vy=0.2}; bz=max(bz,0) }
  version=version==2 ? 3:2
  // Scores are defined once per value and then only referenced, so their corners stay clean.
  let youBase=UInt32(400+(you%10)*10),cpuBase=UInt32(600+(cpu%10)*10)
  let saved=version;version=1
  let flatAll=score(youBase,you,40)+score(cpuBase,cpu,530);version=saved
  let flatNew=flatAll.filter{ e in let id=UInt32(e[1])|UInt32(e[2])<<8|UInt32(e[3])<<16|UInt32(e[4])<<24;return !definedScores.contains(id) }
  for (lens,eye) in [(UInt8(0x10),1.0),(UInt8(0x20),-1.0)] {
   let base:UInt32 = lens==0x10 ? 1000:2000
   var puts:[[UInt8]]=[]
   // CPU paddle (far), ball, your paddle (near frame).
   let (cxp,cyp)=project(cpx,cpy,0);let cs=scale(0);let cd=eye*disparity(0)/2
   puts.append(rect(base,cxp-0.3*W*cs+cd,cyp-0.28*H*cs,0.6*W*cs,0.56*H*cs,9))
   let (bxs,bys)=project(bx,by,bz);let bsz=8+26*scale(bz);let bd=eye*disparity(bz)/2
   puts.append(rect(base+1,bxs-bsz/2+bd,bys-bsz/2,bsz,bsz,15))
   let (pxs,pys)=project(px,py,1);let pw=0.64*W,ph=0.6*H,pd=eye*disparity(1)/2,x0=pxs-pw/2+pd,y0=pys-ph/2
   puts+=[rect(base+2,x0,y0,pw,4,12),rect(base+3,x0,y0+ph-4,pw,4,12),rect(base+4,x0,y0,4,ph,12),rect(base+5,x0+pw-4,y0,4,ph,12)]
   if first { puts+=statics[lens]! }
   puts+=flatNew
   let staticIds:[UInt32] = lens==0x10 ? [100,101,102,103,110,111,112,113]:[200,201,202,203,210,211,212,213]
   let sv:UInt32=1
   var refs:[(UInt32,UInt32)]=staticIds.map{($0,sv)}
   refs+=flatAll.map{(UInt32($0[1])|UInt32($0[2])<<8|UInt32($0[3])<<16|UInt32($0[4])<<24,1)}
   refs+=(0..<6).map{(base+UInt32($0),version)}
   try show(lens,puts,refs)
  }
  for e in flatNew { definedScores.insert(UInt32(e[1])|UInt32(e[2])<<8|UInt32(e[3])<<16|UInt32(e[4])<<24) }
  if first { first=false; staticVersion=version }
  frames+=1
  if now-fpsAt>=2 { print(String(format:"\r%.1f fps  SHOW %.0f ms  you %d : %d cpu   ",Double(frames)/(now-fpsAt),showMs/Double(max(1,showCount)),you,cpu),terminator:"");fflush(stdout);frames=0;fpsAt=now;showMs=0;showCount=0 }
 }
 _=try? session.ownership(.releaseFrame,event:&event);_=try? session.ownership(.releaseWake,event:&event)
 io.close();restore();print("\nbye")
} catch { restore();print("error: \(error)");io.close();exit(1) }
