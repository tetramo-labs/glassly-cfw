package org.memomind.research.hid;

import java.util.Arrays;

/** Android-independent ATT value semantics shared by the APK and JVM tests. */
public final class HidModel {
    private HidModel() {}
    // Keyboard Application, Report ID1: eight modifiers, reserved byte, six usages;
    // output Report ID1: five LED bits + three constant padding bits.
    public static final byte[] REPORT_MAP = hex("05010906a1018501050719e029e7150025017501950881029501750881019506750815002565050719002965810015002501950575010508190129059102950175039101c0");
    public static final byte[] HID_INFO = hex("11010002"); // HID1.11, country0, NormallyConnectable
    public static final byte[] INPUT_REFERENCE = hex("0101");
    public static final byte[] OUTPUT_REFERENCE = hex("0102");
    public static final int OK=0, READ_NOT_PERMITTED=2, WRITE_NOT_PERMITTED=3,
        REQUEST_NOT_SUPPORTED=6, INVALID_OFFSET=7, INVALID_LENGTH=13, FAILURE=257;
    public enum Attribute { INFO, MAP, INPUT, OUTPUT, BOOT_INPUT, BOOT_OUTPUT,
        PROTOCOL, CONTROL, BATTERY, MANUFACTURER, MODEL, FIRMWARE, PNP }
    public static final class Peer {
        public int mtu=23, protocol=1;
        public boolean suspended, reportCccd, bootCccd, notificationPending;
        public byte[] input=new byte[8];
        public byte output;
        public void reset() { mtu=23; protocol=1; suspended=false; reportCccd=false;
            bootCccd=false; notificationPending=false; input=new byte[8]; output=0; }
        public byte[] value(Attribute a) {
            switch(a) {
            case INFO: return HID_INFO.clone(); case MAP: return REPORT_MAP.clone();
            case INPUT: case BOOT_INPUT: return input.clone();
            case OUTPUT: case BOOT_OUTPUT: return new byte[]{output};
            case PROTOCOL: return new byte[]{(byte)protocol};
            case BATTERY: return new byte[]{100};
            case MANUFACTURER: return ascii("Local Research");
            case MODEL: return ascii("MemoMind HID Fixture");
            case FIRMWARE: return ascii("offline-fixture-0.1");
            // Vendor source Bluetooth SIG; zero is a deliberate unassigned test identity.
            // Not a certified product/vendor identifier; do not ship this fixture.
            case PNP: return hex("01000000000100");
            default: return null;
            }
        }
        public int write(Attribute a, byte[] bytes, int offset, boolean prepared) {
            if (prepared) return REQUEST_NOT_SUPPORTED;
            if (offset!=0) return INVALID_OFFSET;
            if (a!=Attribute.OUTPUT && a!=Attribute.BOOT_OUTPUT && a!=Attribute.PROTOCOL && a!=Attribute.CONTROL)
                return WRITE_NOT_PERMITTED;
            if (bytes.length!=1) return INVALID_LENGTH;
            int value=bytes[0]&255;
            if (a==Attribute.PROTOCOL || a==Attribute.CONTROL) {
                if (value>1) return REQUEST_NOT_SUPPORTED;
                if (a==Attribute.PROTOCOL) { protocol=value; input=new byte[8]; }
                else suspended=value==0;
            } else { if ((value&224)!=0) return REQUEST_NOT_SUPPORTED; output=bytes[0]; }
            return OK;
        }
        public int cccd(boolean boot, byte[] bytes, int offset, boolean prepared) {
            if (prepared) return REQUEST_NOT_SUPPORTED;
            if (offset!=0) return INVALID_OFFSET;
            if (bytes.length!=2) return INVALID_LENGTH;
            if (bytes[1]!=0 || (bytes[0]!=0 && bytes[0]!=1)) return REQUEST_NOT_SUPPORTED;
            if (boot) bootCccd=bytes[0]==1; else reportCccd=bytes[0]==1;
            return OK;
        }
        public void validateReport(byte[] bytes) {
            if (bytes.length!=8 || bytes[1]!=0) throw new IllegalArgumentException("report must be8 bytes with reserved byte0; omit Report ID");
            for(int i=2;i<8;i++) {
                int k=bytes[i]&255;
                if (k>101) throw new IllegalArgumentException("usage outside declared keyboard range0..101");
                if(k!=0) for(int j=2;j<i;j++) if(bytes[j]==bytes[i]) throw new IllegalArgumentException("duplicate usage");
            }
            if(suspended) throw new IllegalStateException("host suspended HID");
            if(!(protocol==0?bootCccd:reportCccd)) throw new IllegalStateException("active protocol CCCD not enabled");
            if(notificationPending) throw new IllegalStateException("notification completion pending");
        }
    }
    public static byte[] slice(byte[] bytes,int offset,int mtu) {
        if(offset<0 || offset>bytes.length) throw new IllegalArgumentException("invalid offset");
        return Arrays.copyOfRange(bytes,offset,Math.min(bytes.length,offset+Math.max(0,mtu-1)));
    }
    private static byte[] ascii(String s) { return s.getBytes(java.nio.charset.StandardCharsets.US_ASCII); }
    public static byte[] hex(String s) {
        if(s==null || (s.length()&1)!=0) throw new IllegalArgumentException("even-length hex required");
        byte[] out=new byte[s.length()/2];
        for(int i=0;i<out.length;i++) { int a=Character.digit(s.charAt(i*2),16),b=Character.digit(s.charAt(i*2+1),16);
            if(a<0||b<0) throw new IllegalArgumentException("invalid hex"); out[i]=(byte)((a<<4)|b); }
        return out;
    }
    public static String hex(byte[] b) { StringBuilder s=new StringBuilder(); for(byte v:b)s.append(String.format(java.util.Locale.ROOT,"%02x",v&255));return s.toString(); }
}
