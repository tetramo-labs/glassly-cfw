import org.memomind.research.hid.HidModel;
import static org.memomind.research.hid.HidModel.Attribute;
import java.util.Arrays;
public final class HidModelTest {
 static int checks;
 static void check(boolean b){checks++;if(!b)throw new AssertionError("check "+checks);}
 static void rejected(Runnable r){boolean failed=false;try{r.run();}catch(IllegalArgumentException|IllegalStateException e){failed=true;}check(failed);}
 public static void main(String[] args){
  HidModel.Peer p=new HidModel.Peer();
  check(p.protocol==1&&!p.reportCccd&&!p.bootCccd&&!p.suspended);
  rejected(()->p.validateReport(new byte[8]));
  check(p.cccd(false,HidModel.hex("0100"),0,false)==0);
  p.validateReport(new byte[8]);checks++;
  for(int x=0;x<256;x++){
   byte[] r=new byte[]{0,0,(byte)x,0,0,0,0,0};
   if(x<=101){p.validateReport(r);checks++;}else rejected(()->p.validateReport(r));
  }
  for(int m=0;m<256;m++){p.validateReport(new byte[]{(byte)m,0,4,5,0,0,0,0});checks++;}
  rejected(()->p.validateReport(HidModel.hex("0000040400000000")));
  rejected(()->p.validateReport(new byte[9]));rejected(()->p.validateReport(new byte[7]));
  rejected(()->p.validateReport(HidModel.hex("0001040000000000")));
  p.notificationPending=true;rejected(()->p.validateReport(new byte[8]));p.notificationPending=false;
  for(int value=2;value<256;value++)check(p.cccd(false,new byte[]{(byte)value,0},0,false)==HidModel.REQUEST_NOT_SUPPORTED);
  check(p.reportCccd);check(p.cccd(false,HidModel.hex("0001"),0,false)==HidModel.REQUEST_NOT_SUPPORTED);
  check(p.cccd(false,new byte[1],0,false)==HidModel.INVALID_LENGTH);
  check(p.cccd(false,new byte[2],1,false)==HidModel.INVALID_OFFSET);
  check(p.cccd(false,new byte[2],0,true)==HidModel.REQUEST_NOT_SUPPORTED);check(p.reportCccd);
  check(p.write(Attribute.MAP,new byte[1],0,false)==HidModel.WRITE_NOT_PERMITTED);
  check(p.write(Attribute.PROTOCOL,new byte[]{0},0,true)==HidModel.REQUEST_NOT_SUPPORTED);check(p.protocol==1);
  check(p.write(Attribute.PROTOCOL,new byte[]{0},1,false)==HidModel.INVALID_OFFSET);
  check(p.write(Attribute.PROTOCOL,new byte[]{2},0,false)==HidModel.REQUEST_NOT_SUPPORTED);
  check(p.write(Attribute.PROTOCOL,new byte[2],0,false)==HidModel.INVALID_LENGTH);
  check(p.write(Attribute.PROTOCOL,new byte[]{0},0,false)==0);check(p.protocol==0);
  rejected(()->p.validateReport(new byte[8]));check(p.cccd(true,HidModel.hex("0100"),0,false)==0);p.validateReport(new byte[8]);checks++;
  check(p.write(Attribute.CONTROL,new byte[]{0},0,false)==0);rejected(()->p.validateReport(new byte[8]));
  check(p.write(Attribute.CONTROL,new byte[]{1},0,false)==0);p.validateReport(new byte[8]);checks++;
  for(int v=0;v<256;v++){int rc=p.write(Attribute.OUTPUT,new byte[]{(byte)v},0,false);check(rc==(v<32?0:HidModel.REQUEST_NOT_SUPPORTED));}
  check(p.value(Attribute.OUTPUT)[0]==31);check(p.value(Attribute.BOOT_OUTPUT)[0]==31);
  for(int mtu:new int[]{23,40,64,247,517}){
   byte[] map=p.value(Attribute.MAP);java.io.ByteArrayOutputStream got=new java.io.ByteArrayOutputStream();
   for(int off=0;off<map.length;){byte[] part=HidModel.slice(map,off,mtu);check(part.length<=mtu-1);got.write(part,0,part.length);off+=part.length;}
   check(Arrays.equals(map,got.toByteArray()));check(HidModel.slice(map,map.length,mtu).length==0);
   rejected(()->HidModel.slice(map,-1,mtu));rejected(()->HidModel.slice(map,map.length+1,mtu));
  }
  byte[] map=p.value(Attribute.MAP);map[0]=0;check(p.value(Attribute.MAP)[0]==5);
  p.reset();check(p.protocol==1&&p.mtu==23&&!p.reportCccd&&!p.bootCccd&&!p.notificationPending&&!p.suspended&&p.output==0);
  rejected(()->HidModel.hex("x0"));rejected(()->HidModel.hex("0"));
  check(Arrays.equals(HidModel.hex(HidModel.hex(HidModel.REPORT_MAP)),HidModel.REPORT_MAP));
  System.out.println("checks="+checks);System.out.println("report_map="+HidModel.hex(HidModel.REPORT_MAP));
  System.out.println("hid_info="+HidModel.hex(HidModel.HID_INFO));System.out.println("input_reference="+HidModel.hex(HidModel.INPUT_REFERENCE));System.out.println("output_reference="+HidModel.hex(HidModel.OUTPUT_REFERENCE));
 }
}
