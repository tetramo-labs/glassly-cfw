package org.memomind.research.hid;
import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.widget.*;
import java.util.UUID;

/** Permission/start/stop UI only. Activity visibility never tears down the service. */
public final class HidActivity extends Activity {
    private TextView status;
    private String token;
    private int port;
    private boolean requestedStart;
    @Override public void onCreate(Bundle state){
        super.onCreate(state);
        token=getIntent().getStringExtra("token");
        if(token==null)token=state==null?UUID.randomUUID().toString().replace("-",""):state.getString("token");
        port=getIntent().getIntExtra("port",38742);
        LinearLayout box=new LinearLayout(this);box.setOrientation(1);box.setPadding(24,32,24,24);
        status=new TextView(this);box.addView(status);
        Button permissions=new Button(this);permissions.setText("Grant Bluetooth and notification permissions");
        permissions.setOnClickListener(v->requestPermissions(new String[]{Manifest.permission.BLUETOOTH_CONNECT,Manifest.permission.BLUETOOTH_ADVERTISE,Manifest.permission.POST_NOTIFICATIONS},1));box.addView(permissions);
        Button start=new Button(this);start.setText("Start bounded controller service (BLE remains off)");start.setOnClickListener(v->startController());box.addView(start);
        Button stop=new Button(this);stop.setText("STOP fixture and controller service");stop.setOnClickListener(v->stopService(new Intent(this,HidService.class)));box.addView(stop);
        setContentView(box);
        status.setText("HID test fixture\nToken for a NEW service: "+token+"\nPort: "+port+"\nAn existing service keeps its original token. Check its notification. Switching apps or pairing UI does not stop it. No automatic typing.");
        requestedStart=state==null&&getIntent().getBooleanExtra("start_controller",false);
    }
    @Override public void onPostResume(){super.onPostResume();if(requestedStart){requestedStart=false;startController();}}
    private void startController(){
        for(String p:new String[]{Manifest.permission.BLUETOOTH_CONNECT,Manifest.permission.BLUETOOTH_ADVERTISE,Manifest.permission.POST_NOTIFICATIONS})
            if(checkSelfPermission(p)!=PackageManager.PERMISSION_GRANTED){status.append("\nGrant permissions, then press Start.");return;}
        NotificationManager n=getSystemService(NotificationManager.class);
        n.createNotificationChannel(new NotificationChannel(HidService.CHANNEL,"HID fixture controller",NotificationManager.IMPORTANCE_LOW));
        if(!n.areNotificationsEnabled()||n.getNotificationChannel(HidService.CHANNEL).getImportance()==NotificationManager.IMPORTANCE_NONE){status.append("\nEnable visible fixture notifications before starting.");return;}
        if(token==null||token.length()<32||token.length()>128||port<1024||port>65535){status.append("\nInvalid token/port");return;}
        try{startForegroundService(new Intent(this,HidService.class).setAction(HidService.ACTION_START).putExtra("token",token).putExtra("port",port));status.append("\nController service requested. Check notification; BLE is still off.");}
        catch(RuntimeException e){status.append("\nService start rejected: "+e.getClass().getSimpleName());}
    }
    @Override public void onSaveInstanceState(Bundle state){state.putString("token",token);super.onSaveInstanceState(state);}
    // No onStop/onDestroy stopService: pairing dialogs and app switching are expected.
}
