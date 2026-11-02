package org.memomind.research.hid;

import android.Manifest;
import android.app.*;
import android.content.pm.ServiceInfo;
import android.bluetooth.*;
import android.bluetooth.le.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.os.*;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.ArrayBlockingQueue;
import org.json.*;
import static org.memomind.research.hid.HidModel.Attribute;

/** Bounded connected-device foreground service. UI visibility does not own BLE lifetime. */
public final class HidService extends Service {
    private final Object lock=new Object();
    private final Map<BluetoothGattCharacteristic,Attribute> attributes=new IdentityHashMap<>();
    private final HidModel.Peer model=new HidModel.Peer();
    private BluetoothAdapter adapter;
    private BluetoothGattServer gatt;
    private BluetoothLeAdvertiser advertiser;
    private AdvertiseCallback advertisingCallback;
    private BluetoothDevice peer;
    private BluetoothGattCharacteristic input,bootInput;
    private final List<BluetoothGattService> services=new ArrayList<>();
    private int serviceIndex,generation,port=38742;
    private boolean advertising,starting,encrypted=true;
    private volatile boolean closed;
    private ServerSocket listener;
    private volatile Session session;
    private String token;
    public static final String ACTION_START="org.memomind.research.hid.START";
    public static final String ACTION_STOP="org.memomind.research.hid.STOP";
    public static final String CHANNEL="hid-fixture";
    private static final int NOTIFICATION_ID=4201;
    private final Handler main=new Handler(Looper.getMainLooper());
    private ControllerLease lease;
    private boolean initialized, receiverRegistered;
    private String notificationState="Waiting for authenticated controller; BLE off";
    private final Runnable watchdog=new Runnable(){public void run(){synchronized(lock){
        if(closed)return;
        if(lease==null||lease.expired(SystemClock.elapsedRealtime())){shutdown("controller lease expired");return;}
        if(!notificationsVisible()){shutdown("notification unavailable");return;}
        updateNotification();main.postDelayed(this,1000);
    }}};
    private static final UUID CCCD=uuid(0x2902),REFERENCE=uuid(0x2908);
    private static UUID uuid(int n) {return UUID.fromString(String.format(Locale.ROOT,"0000%04x-0000-1000-8000-00805f9b34fb",n));}
    private static JSONObject obj(Object... pairs) {
        JSONObject o=new JSONObject();try {for(int i=0;i<pairs.length;i+=2)o.put((String)pairs[i],pairs[i+1]);}catch(JSONException e){throw new IllegalArgumentException(e);}return o;
    }
    private void display(String s){notificationState=s;main.post(()->{synchronized(lock){if(initialized&&!closed)updateNotification();}});}
    private boolean notificationsVisible(){
        NotificationManager n=getSystemService(NotificationManager.class);
        NotificationChannel c=n.getNotificationChannel(CHANNEL);
        return checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)==PackageManager.PERMISSION_GRANTED && n.areNotificationsEnabled() && c!=null && c.getImportance()!=NotificationManager.IMPORTANCE_NONE;
    }
    private Notification notification(){
        Intent stop=new Intent(this,HidService.class).setAction(ACTION_STOP);
        PendingIntent cancel=PendingIntent.getService(this,1,stop,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        PendingIntent open=PendingIntent.getActivity(this,2,new Intent(this,HidActivity.class),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        long left=lease==null?0:lease.remaining(SystemClock.elapsedRealtime())/1000;
        return new Notification.Builder(this,CHANNEL).setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setForegroundServiceBehavior(Notification.FOREGROUND_SERVICE_IMMEDIATE)
            .setContentTitle("MemoMind HID fixture — "+left+"s lease")
            .setContentText(notificationState).setContentIntent(open).setDeleteIntent(cancel).setOngoing(true).setOnlyAlertOnce(true)
            .addAction(new Notification.Action.Builder(null,"STOP",cancel).build()).build();
    }
    private void updateNotification(){getSystemService(NotificationManager.class).notify(NOTIFICATION_ID,notification());}
    @Override public IBinder onBind(Intent intent){return null;}
    @Override public int onStartCommand(Intent intent,int flags,int startId){synchronized(lock){
        if(intent==null){stopSelf();return START_NOT_STICKY;}
        if(ACTION_STOP.equals(intent.getAction())){shutdown("explicit UI/notification STOP");return START_NOT_STICKY;}
        if(initialized)return START_NOT_STICKY; // Reopening UI never replaces an active token/session.
        if(!ACTION_START.equals(intent.getAction())){stopSelf();return START_NOT_STICKY;}
        token=intent.getStringExtra("token");port=intent.getIntExtra("port",38742);
        if(token==null||token.length()<32||token.length()>128||port<1024||port>65535){stopSelf();return START_NOT_STICKY;}
        try{
            if(checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT)!=PackageManager.PERMISSION_GRANTED||checkSelfPermission(Manifest.permission.BLUETOOTH_ADVERTISE)!=PackageManager.PERMISSION_GRANTED)throw new IllegalStateException("Bluetooth permissions missing");
            NotificationManager n=getSystemService(NotificationManager.class);
            n.createNotificationChannel(new NotificationChannel(CHANNEL,"HID fixture controller",NotificationManager.IMPORTANCE_LOW));
            if(!notificationsVisible())throw new IllegalStateException("visible notifications required");
            lease=new ControllerLease(SystemClock.elapsedRealtime());
            startForeground(NOTIFICATION_ID,notification(),ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE);
            initialized=true;
            BluetoothManager manager=getSystemService(BluetoothManager.class);adapter=manager==null?null:manager.getAdapter();
            IntentFilter filter=new IntentFilter();filter.addAction(BluetoothDevice.ACTION_BOND_STATE_CHANGED);filter.addAction(BluetoothDevice.ACTION_PAIRING_REQUEST);filter.addAction(BluetoothAdapter.ACTION_STATE_CHANGED);
            registerReceiver(receiver,filter,Context.RECEIVER_EXPORTED);receiverRegistered=true;
            listener=new ServerSocket();listener.bind(new InetSocketAddress("127.0.0.1",port),1);
            new Thread(this::accept,"hid-loopback").start();main.post(watchdog);
        }catch(Exception e){shutdown("service start failed: "+e.getClass().getSimpleName());}
        return START_NOT_STICKY;
    }}
    private void shutdown(String reason){synchronized(lock){
        if(closed)return;
        event("service_stopping","reason",reason);
        if(lease!=null)lease.stop();
        stopPeripheral(reason);closed=true;main.removeCallbacks(watchdog);
        if(session!=null)session.close();
        try{if(listener!=null)listener.close();}catch(IOException ignored){}
        if(receiverRegistered){unregisterReceiver(receiver);receiverRegistered=false;}
        stopForeground(STOP_FOREGROUND_REMOVE);stopSelf();
    }}
    @Override public void onDestroy(){shutdown("service destroyed");super.onDestroy();}
    private void event(String name,Object...fields) {
        JSONObject o=obj("event",name,"elapsedRealtimeNanos",SystemClock.elapsedRealtimeNanos());
        try {for(int i=0;i<fields.length;i+=2)o.put((String)fields[i],fields[i+1]);}catch(JSONException e){throw new IllegalArgumentException(e);}
        Session target=session;if(target!=null)target.emit(o);
    }
    private final BroadcastReceiver receiver=new BroadcastReceiver(){@Override public void onReceive(Context c,Intent i){synchronized(lock){
        BluetoothDevice d=i.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE,BluetoothDevice.class);
        if(BluetoothAdapter.ACTION_STATE_CHANGED.equals(i.getAction())) {
            int state=i.getIntExtra(BluetoothAdapter.EXTRA_STATE,-1);event("adapter_state","state",state);
            if(state!=BluetoothAdapter.STATE_ON)shutdown("adapter not on");
        }else if(d!=null && peer!=null && d.equals(peer)) {
            if(BluetoothDevice.ACTION_BOND_STATE_CHANGED.equals(i.getAction()))event("bond","address",d.getAddress(),"state",i.getIntExtra(BluetoothDevice.EXTRA_BOND_STATE,-1),"previous",i.getIntExtra(BluetoothDevice.EXTRA_PREVIOUS_BOND_STATE,-1));
            else event("pairing_request","address",d.getAddress(),"variant",i.getIntExtra(BluetoothDevice.EXTRA_PAIRING_VARIANT,-1));
            // Never read EXTRA_PAIRING_KEY; never confirm, set PIN/passkey or abort broadcasts.
        }
    }}};
    private void requirePermissions(){
        if(checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT)!=PackageManager.PERMISSION_GRANTED || checkSelfPermission(Manifest.permission.BLUETOOTH_ADVERTISE)!=PackageManager.PERMISSION_GRANTED)throw new IllegalStateException("grant CONNECT and ADVERTISE first");
        if(adapter==null||!adapter.isEnabled())throw new IllegalStateException("Bluetooth disabled/unavailable");
    }
    private BluetoothGattCharacteristic characteristic(BluetoothGattService s,int id,int props,Attribute a,boolean secure) {
        int permissions=0;
        if((props&BluetoothGattCharacteristic.PROPERTY_READ)!=0)permissions|=secure?BluetoothGattCharacteristic.PERMISSION_READ_ENCRYPTED:BluetoothGattCharacteristic.PERMISSION_READ;
        if((props&(BluetoothGattCharacteristic.PROPERTY_WRITE|BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE))!=0)permissions|=secure?BluetoothGattCharacteristic.PERMISSION_WRITE_ENCRYPTED:BluetoothGattCharacteristic.PERMISSION_WRITE;
        BluetoothGattCharacteristic c=new BluetoothGattCharacteristic(uuid(id),props,permissions);attributes.put(c,a);s.addCharacteristic(c);return c;
    }
    private void reference(BluetoothGattCharacteristic c,byte[] value){BluetoothGattDescriptor d=new BluetoothGattDescriptor(REFERENCE,encrypted?BluetoothGattDescriptor.PERMISSION_READ_ENCRYPTED:BluetoothGattDescriptor.PERMISSION_READ);d.setValue(value);c.addDescriptor(d);}
    private void cccd(BluetoothGattCharacteristic c){int p=encrypted?(BluetoothGattDescriptor.PERMISSION_READ_ENCRYPTED|BluetoothGattDescriptor.PERMISSION_WRITE_ENCRYPTED):(BluetoothGattDescriptor.PERMISSION_READ|BluetoothGattDescriptor.PERMISSION_WRITE);c.addDescriptor(new BluetoothGattDescriptor(CCCD,p));}
    private void makeServices(){
        final int R=BluetoothGattCharacteristic.PROPERTY_READ,W=BluetoothGattCharacteristic.PROPERTY_WRITE,N=BluetoothGattCharacteristic.PROPERTY_NOTIFY,U=BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE;
        BluetoothGattService hid=new BluetoothGattService(uuid(0x1812),BluetoothGattService.SERVICE_TYPE_PRIMARY);
        characteristic(hid,0x2a4a,R,Attribute.INFO,encrypted);characteristic(hid,0x2a4b,R,Attribute.MAP,encrypted);
        input=characteristic(hid,0x2a4d,R|N,Attribute.INPUT,encrypted);reference(input,HidModel.INPUT_REFERENCE);cccd(input);
        BluetoothGattCharacteristic output=characteristic(hid,0x2a4d,R|W|U,Attribute.OUTPUT,encrypted);reference(output,HidModel.OUTPUT_REFERENCE);
        characteristic(hid,0x2a4e,R|U,Attribute.PROTOCOL,encrypted);characteristic(hid,0x2a4c,U,Attribute.CONTROL,encrypted);
        bootInput=characteristic(hid,0x2a22,R|N,Attribute.BOOT_INPUT,encrypted);cccd(bootInput);
        characteristic(hid,0x2a32,R|W|U,Attribute.BOOT_OUTPUT,encrypted);services.add(hid);
        BluetoothGattService battery=new BluetoothGattService(uuid(0x180f),BluetoothGattService.SERVICE_TYPE_PRIMARY);
        characteristic(battery,0x2a19,R,Attribute.BATTERY,false);services.add(battery);
        BluetoothGattService info=new BluetoothGattService(uuid(0x180a),BluetoothGattService.SERVICE_TYPE_PRIMARY);
        characteristic(info,0x2a29,R,Attribute.MANUFACTURER,false);characteristic(info,0x2a24,R,Attribute.MODEL,false);characteristic(info,0x2a26,R,Attribute.FIRMWARE,false);characteristic(info,0x2a50,R,Attribute.PNP,false);services.add(info);
    }
    private JSONObject start(JSONObject q) throws JSONException {
        requirePermissions();if(gatt!=null)throw new IllegalStateException("already started/starting");
        String security=q.optString("security","encrypted");if(!security.equals("encrypted")&&!security.equals("open"))throw new IllegalArgumentException("security must be encrypted or open");
        encrypted=security.equals("encrypted");advertiser=adapter.getBluetoothLeAdvertiser();if(advertiser==null)throw new IllegalStateException("BLE advertiser unavailable");
        String name=adapter.getName();if(name==null||name.isEmpty())throw new IllegalStateException("existing adapter name is empty; no automatic rename");
        starting=true;int gen=++generation;model.reset();makeServices();
        try {gatt=getSystemService(BluetoothManager.class).openGattServer(this,callbacks(gen));if(gatt==null)throw new IllegalStateException("openGattServer failed");
            serviceIndex=0;if(!gatt.addService(services.get(0)))throw new IllegalStateException("addService rejected");
        }catch(RuntimeException e){stopPeripheral("start failed");throw e;}
        return obj("accepted",true,"state","registering","security",security,"generation",gen);
    }
    private void advertise(int gen){
        advertisingCallback=new AdvertiseCallback(){@Override public void onStartSuccess(AdvertiseSettings s){synchronized(lock){if(gen!=generation)return;advertising=true;starting=false;event("advertising","generation",gen,"security",encrypted?"encrypted":"open");display("Advertising; inject reports only explicitly");}}
            @Override public void onStartFailure(int error){synchronized(lock){if(gen!=generation)return;event("advertising_failed","error",error);stopPeripheral("advertising failed");}}};
        AdvertiseSettings settings=new AdvertiseSettings.Builder().setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY).setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_LOW).setConnectable(true).setTimeout(0).build();
        AdvertiseData data=new AdvertiseData.Builder().addServiceUuid(new ParcelUuid(uuid(0x1812))).build();
        AdvertiseData scan=new AdvertiseData.Builder().setIncludeDeviceName(true).build();
        advertiser.startAdvertising(settings,data,scan,advertisingCallback);
    }
    private void stopPeripheral(String why){
        ++generation;starting=false;advertising=false;
        if(advertiser!=null&&advertisingCallback!=null)try{advertiser.stopAdvertising(advertisingCallback);}catch(RuntimeException ignored){}
        advertisingCallback=null;advertiser=null;
        if(gatt!=null){try{if(peer!=null)gatt.cancelConnection(peer);}catch(RuntimeException ignored){}try{gatt.close();}catch(RuntimeException ignored){}gatt=null;event("stopped","reason",why);}
        peer=null;model.reset();services.clear();attributes.clear();input=null;bootInput=null;
        display("BLE off; explicit start required");
    }
    private boolean live(int gen,BluetoothDevice d){return gen==generation&&gatt!=null&&peer!=null&&peer.equals(d);}
    private void response(BluetoothDevice d,int id,int status,int offset,byte[] bytes){
        boolean accepted=gatt.sendResponse(d,id,status,offset,bytes);event("att_response","requestId",id,"status",status,"offset",offset,"bytes",bytes==null?0:bytes.length,"accepted",accepted);
    }
    private void read(BluetoothDevice d,int id,int offset,byte[] value){
        if(value==null){response(d,id,HidModel.READ_NOT_PERMITTED,offset,null);return;}
        if(offset<0||offset>value.length){response(d,id,HidModel.INVALID_OFFSET,offset,null);return;}
        response(d,id,HidModel.OK,offset,HidModel.slice(value,offset,model.mtu));
    }
    private BluetoothGattServerCallback callbacks(final int gen){return new BluetoothGattServerCallback(){
        @Override public void onServiceAdded(int result,BluetoothGattService s){synchronized(lock){
            if(gen!=generation||gatt==null)return;event("service_added","uuid",s.getUuid().toString(),"status",result);
            if(result!=BluetoothGatt.GATT_SUCCESS||!s.getUuid().equals(services.get(serviceIndex).getUuid())){stopPeripheral("service registration failed");return;}
            if(++serviceIndex<services.size()){if(!gatt.addService(services.get(serviceIndex)))stopPeripheral("addService rejected");}
            else try{advertise(gen);}catch(RuntimeException e){event("advertising_failed","error",e.getClass().getSimpleName());stopPeripheral("advertising exception");}
        }}
        @Override public void onConnectionStateChange(BluetoothDevice d,int result,int state){synchronized(lock){
            if(gen!=generation||gatt==null)return;event("connection","address",d.getAddress(),"status",result,"state",state,"bondState",d.getBondState());
            if(state==BluetoothProfile.STATE_CONNECTED){
                if(result!=BluetoothGatt.GATT_SUCCESS){gatt.cancelConnection(d);event("connection_rejected","reason","nonzero status");return;}
                if(peer!=null&&!peer.equals(d)){event("extra_peer_rejected","address",d.getAddress());gatt.cancelConnection(d);return;}
                peer=d;model.reset();display("Connected HID peer; reports are manual");if(advertiser!=null&&advertisingCallback!=null)advertiser.stopAdvertising(advertisingCallback);advertising=false;
            }else if(state==BluetoothProfile.STATE_DISCONNECTED&&peer!=null&&peer.equals(d)){stopPeripheral("peer disconnected; explicit start required");}
        }}
        @Override public void onMtuChanged(BluetoothDevice d,int mtu){synchronized(lock){if(live(gen,d)){model.mtu=Math.max(23,Math.min(517,mtu));event("mtu","value",mtu);}}}
        @Override public void onCharacteristicReadRequest(BluetoothDevice d,int id,int offset,BluetoothGattCharacteristic c){synchronized(lock){if(!live(gen,d))return;Attribute a=attributes.get(c);event("read","requestId",id,"attribute",String.valueOf(a),"offset",offset);read(d,id,offset,a==null?null:model.value(a));}}
        @Override public void onCharacteristicWriteRequest(BluetoothDevice d,int id,BluetoothGattCharacteristic c,boolean prepared,boolean needsResponse,int offset,byte[] value){synchronized(lock){
            if(!live(gen,d))return;Attribute a=attributes.get(c);int result=model.write(a,value,offset,prepared);
            event("write","requestId",id,"attribute",String.valueOf(a),"prepared",prepared,"responseNeeded",needsResponse,"offset",offset,"hex",HidModel.hex(value),"status",result);
            if(needsResponse)response(d,id,result,offset,null);
        }}
        @Override public void onDescriptorReadRequest(BluetoothDevice d,int id,int offset,BluetoothGattDescriptor desc){synchronized(lock){
            if(!live(gen,d))return;Attribute a=attributes.get(desc.getCharacteristic());byte[] value=null;
            if(desc.getUuid().equals(CCCD))value=new byte[]{(byte)((a==Attribute.BOOT_INPUT?model.bootCccd:model.reportCccd)?1:0),0};
            else if(desc.getUuid().equals(REFERENCE))value=desc.getValue();
            event("descriptor_read","requestId",id,"attribute",String.valueOf(a),"uuid",desc.getUuid().toString(),"offset",offset);read(d,id,offset,value);
        }}
        @Override public void onDescriptorWriteRequest(BluetoothDevice d,int id,BluetoothGattDescriptor desc,boolean prepared,boolean needsResponse,int offset,byte[] value){synchronized(lock){
            if(!live(gen,d))return;Attribute a=attributes.get(desc.getCharacteristic());int result=desc.getUuid().equals(CCCD)?model.cccd(a==Attribute.BOOT_INPUT,value,offset,prepared):HidModel.WRITE_NOT_PERMITTED;
            event("descriptor_write","requestId",id,"attribute",String.valueOf(a),"uuid",desc.getUuid().toString(),"offset",offset,"prepared",prepared,"responseNeeded",needsResponse,"hex",HidModel.hex(value),"status",result);
            if(needsResponse)response(d,id,result,offset,null);
        }}
        @Override public void onExecuteWrite(BluetoothDevice d,int id,boolean execute){synchronized(lock){if(!live(gen,d))return;event("execute_write","execute",execute);response(d,id,HidModel.REQUEST_NOT_SUPPORTED,0,null);}}
        @Override public void onNotificationSent(BluetoothDevice d,int result){synchronized(lock){if(live(gen,d)){model.notificationPending=false;event("notification_sent","status",result);}}}
    };}
    private JSONObject command(JSONObject q)throws Exception{synchronized(lock){
        String op=q.getString("op");event("control","op",op);
        if(op.equals("stop")){
            if(lease!=null)lease.stop();stopPeripheral("controller stop");
            main.postDelayed(()->shutdown("controller stop"),250);
            return obj("stopped",true,"serviceClosing",true);
        }
        if(closed||lease==null)throw new IllegalStateException("service closed");
        lease.request(SystemClock.elapsedRealtime());
        switch(op){
        case "status":return obj("starting",starting,"advertising",advertising,"registered",gatt!=null&&!starting,"connected",peer!=null,"address",peer==null?JSONObject.NULL:peer.getAddress(),"protocol",model.protocol,"suspended",model.suspended,"reportCccd",model.reportCccd,"bootCccd",model.bootCccd,"notificationPending",model.notificationPending,"mtu",model.mtu,"security",encrypted?"encrypted":"open","generation",generation,"leaseRemainingMs",lease.remaining(SystemClock.elapsedRealtime()),"hardDeadlineElapsedMs",lease.hardDeadline());
        case "start":return start(q);
        case "report":case "release":
            requirePermissions();if(peer==null||gatt==null)throw new IllegalStateException("no fixture peer");
            byte[] report=op.equals("release")?new byte[8]:HidModel.hex(q.getString("hex"));model.validateReport(report);
            model.notificationPending=true;
            int result;try{result=gatt.notifyCharacteristicChanged(peer,model.protocol==0?bootInput:input,false,report.clone());}
            catch(RuntimeException e){model.notificationPending=false;throw e;}
            if(result!=BluetoothStatusCodes.SUCCESS){model.notificationPending=false;throw new IllegalStateException("notification submission status"+result);}
            model.input=report.clone();event("report_submitted","hex",HidModel.hex(report),"protocol",model.protocol);
            return obj("submitted",true,"hex",HidModel.hex(report),"note","await notification_sent; not proof of host action");
        default:throw new IllegalArgumentException("unknown op");
        }
    }}
    private void accept(){while(!closed){try{Socket s=listener.accept();s.setTcpNoDelay(true);s.setSoTimeout(120000);synchronized(lock){if(closed||session!=null){s.close();continue;}session=new Session(s);session.start();}}catch(IOException e){if(!closed)display("Listener stopped");return;}}}
    private final class Session extends Thread {
        private final Socket socket;private final ArrayBlockingQueue<String> out=new ArrayBlockingQueue<>(1024);private volatile boolean done,overflow;
        private final File log;
        Session(Socket s){super("hid-controller");socket=s;log=new File(getFilesDir(),"hid-"+System.currentTimeMillis()+".jsonl");}
        void emit(JSONObject o){if(!done&&!out.offer(o.toString())){overflow=true;done=true;try{socket.close();}catch(IOException ignored){}main.post(()->{synchronized(lock){shutdown("log queue overflow");}});}}
        void close(){done=true;try{socket.close();}catch(IOException ignored){}}
        @Override public void run(){Thread writer=null;try{
            InputStream in=socket.getInputStream();JSONObject hello=new JSONObject(line(in));
            String provided=hello.optString("token","");
            if(!hello.optString("op").equals("hello")||!MessageDigest.isEqual(token.getBytes(StandardCharsets.UTF_8),provided.getBytes(StandardCharsets.UTF_8)))throw new IOException("authentication failed");
            synchronized(lock){if(closed||lease==null)throw new IOException("service closed");lease.authenticate(SystemClock.elapsedRealtime());display("Authenticated controller; BLE off until explicit start");}
            writer=new Thread(()->writeLoop(),"hid-log-writer");writer.start();
            emit(obj("id",hello.opt("id"),"ok",true,"result",obj("protocol",1,"port",port,"log",log.getName(),"idleTimeoutSeconds",120,"hardLeaseSeconds",600,"bleStarted",false)));
            while(!done){JSONObject q=new JSONObject(line(in));try {JSONObject result=command(q);emit(obj("id",q.opt("id"),"ok",true,"result",result));}catch(Exception e){emit(obj("id",q.opt("id"),"ok",false,"error",e.getClass().getSimpleName()+": "+e.getMessage()));}}
        }catch(Exception e){event("controller_closed","reason",e.getClass().getSimpleName());}
        finally{synchronized(lock){shutdown("controller closed/idle timeout");if(session==this)session=null;}close();if(writer!=null)try{writer.join(1000);}catch(InterruptedException e){Thread.currentThread().interrupt();}}}
        private void writeLoop(){try(BufferedWriter file=new BufferedWriter(new OutputStreamWriter(new FileOutputStream(log),StandardCharsets.UTF_8));BufferedWriter wire=new BufferedWriter(new OutputStreamWriter(socket.getOutputStream(),StandardCharsets.UTF_8))){
            boolean wireAlive=true;
            while(!done||!out.isEmpty()){String value=out.poll(250,java.util.concurrent.TimeUnit.MILLISECONDS);if(value==null)continue;file.write(value);file.newLine();file.flush();
                if(wireAlive)try{wire.write(value);wire.newLine();wire.flush();}catch(IOException e){wireAlive=false;close();}}

            if(overflow){file.write(obj("event","log_overflow","lossless",false).toString());file.newLine();file.flush();}
        }catch(Exception e){close();}}
        private String line(InputStream in)throws IOException{ByteArrayOutputStream b=new ByteArrayOutputStream();for(int v;(v=in.read())!=-1;){if(v==10)return b.toString("UTF-8");if(b.size()>=4096)throw new IOException("line too long");b.write(v);}throw new EOFException();}
    }
}
