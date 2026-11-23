package org.memomind.research.bridge;

import android.Manifest;
import android.app.Activity;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothSocket;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.*;
import org.json.JSONObject;

/** Task-local loopback bridge. Connecting never sends an application command. */
public final class BridgeActivity extends Activity {
    private TextView status;
    private Server server;
    private int port = 38741;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        port = getIntent().getIntExtra("port", 38741);
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(32, 48, 32, 32);
        status = new TextView(this);
        status.setTextSize(18);
        layout.addView(status);
        Button start = new Button(this);
        start.setText("Start bridge");
        start.setOnClickListener(v -> startBridge());
        layout.addView(start);
        Button stop = new Button(this);
        stop.setText("Stop bridge");
        stop.setOnClickListener(v -> stopBridge());
        layout.addView(stop);
        setContentView(layout);
        startBridge();
    }

    private void display(String message) {
        runOnUiThread(() -> status.setText("MemoMind RFCOMM Bridge\n\n" + message));
    }

    private void startBridge() {
        if (checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) {
            display("Bluetooth permission is required.");
            requestPermissions(new String[]{Manifest.permission.BLUETOOTH_CONNECT}, 1);
            return;
        }
        if (server != null) return;
        if (port < 1024 || port > 65535) {
            display("Invalid loopback port.");
            return;
        }
        try {
            server = new Server(port);
            server.start();
        } catch (IOException ex) {
            display("Cannot start: " + ex.getMessage());
        }
    }

    private void stopBridge() {
        if (server != null) server.close();
        server = null;
        display("Stopped. Bluetooth sockets are closed.");
    }

    @Override public void onRequestPermissionsResult(int request, String[] permissions, int[] grants) {
        super.onRequestPermissionsResult(request, permissions, grants);
        if (grants.length > 0 && grants[0] == PackageManager.PERMISSION_GRANTED) startBridge();
        else display("Bluetooth permission denied. Grant it, then tap Start bridge.");
    }

    @Override public void onDestroy() {
        stopBridge();
        super.onDestroy();
    }

    private final class Server extends Thread implements Closeable {
        private final ServerSocket listener;
        private final Set<Session> sessions = new HashSet<>();
        private volatile boolean stopped;
        Server(int port) throws IOException {
            super("memomind-loopback-server");
            listener = new ServerSocket();
            listener.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), port), 2);
        }
        @Override public void run() {
            display("Listening on 127.0.0.1:" + port + "\nNo glasses connection.\nKeep this Activity open.");
            while (!stopped) {
                try {
                    Socket client = listener.accept();
                    client.setTcpNoDelay(true);
                    Session next = new Session(client);
                    synchronized (this) {
                        if (stopped || sessions.size() >= 2) {
                            next.close();
                            continue;
                        }
                        sessions.add(next);
                    }
                    new Thread(() -> {
                        try { next.run(); }
                        finally { synchronized (Server.this) { sessions.remove(next); } }
                    }, "memomind-host-session").start();
                } catch (Exception ex) {
                    if (!stopped) display("Bridge error: " + ex.getMessage());
                }
            }
        }
        @Override public void close() {
            stopped = true;
            try { listener.close(); } catch (IOException ignored) {}
            synchronized (this) {
                for (Session current : sessions) current.close();
                sessions.clear();
            }
        }
    }

    private final class Session implements Closeable {
        private final Socket client;
        private final BufferedReader input;
        private final BufferedWriter output;
        private final ScheduledExecutorService timer = Executors.newSingleThreadScheduledExecutor();
        private volatile BluetoothSocket bluetooth;
        private volatile boolean closed;
        private volatile String address;
        private volatile String service;

        Session(Socket client) throws IOException {
            this.client = client;
            input = new BufferedReader(new InputStreamReader(client.getInputStream(), StandardCharsets.UTF_8));
            output = new BufferedWriter(new OutputStreamWriter(client.getOutputStream(), StandardCharsets.UTF_8));
        }

        private synchronized void send(JSONObject object) throws IOException {
            output.write(object.toString());
            output.newLine();
            output.flush();
        }

        void run() {
            try {
                send(new JSONObject().put("event", "ready").put("protocol", 1).put("maxSessions", 2));
                String line;
                while (!closed && (line = input.readLine()) != null) {
                    Object id = JSONObject.NULL;
                    try {
                        JSONObject command = new JSONObject(line);
                        id = command.get("id");
                        JSONObject result = handle(command);
                        send(new JSONObject().put("id", id).put("ok", true).put("result", result));
                    } catch (Exception ex) {
                        send(new JSONObject().put("id", id).put("ok", false)
                            .put("error", ex.getClass().getSimpleName() + ": " + ex.getMessage()));
                    }
                }
            } catch (Exception ex) {
                if (!closed) display("Host disconnected: " + ex.getMessage());
            } finally {
                close();
            }
        }

        private JSONObject handle(JSONObject command) throws Exception {
            switch (command.getString("op")) {
                case "status":
                    return new JSONObject().put("connected", bluetooth != null && bluetooth.isConnected())
                        .put("address", address).put("service", service);
                case "connect":
                    disconnect();
                    String mac = command.getString("address");
                    if (!BluetoothAdapter.checkBluetoothAddress(mac)) throw new IOException("Expected uppercase Bluetooth MAC address");
                    String selected = command.getString("service");
                    String uuid;
                    if (selected.equals("control")) uuid = "00007033-0000-1000-8000-00805f9b34fb";
                    else if (selected.equals("ota")) uuid = "00007034-0000-1000-8000-00805f9b34fb";
                    else throw new IOException("service must be control or ota");
                    BluetoothManager manager = getSystemService(BluetoothManager.class);
                    BluetoothAdapter adapter = manager == null ? null : manager.getAdapter();
                    if (adapter == null || !adapter.isEnabled()) throw new IOException("Bluetooth adapter unavailable or disabled");
                    BluetoothSocket socket = adapter.getRemoteDevice(mac).createRfcommSocketToServiceRecord(UUID.fromString(uuid));
                    bluetooth = socket;
                    ScheduledFuture<?> timeout = timer.schedule(() -> {
                        try { socket.close(); } catch (IOException ignored) {}
                    }, 15, TimeUnit.SECONDS);
                    try {
                        socket.connect();
                        if (closed) throw new IOException("Host session closed during connection");
                    } catch (Exception ex) {
                        disconnect();
                        throw ex;
                    } finally { timeout.cancel(false); }
                    address = mac;
                    service = selected;
                    display("Connected to " + mac + "\nService: " + selected + "\nLoopback port: " + port);
                    new Thread(() -> readBluetooth(socket), "memomind-rfcomm-reader").start();
                    return new JSONObject().put("address", mac).put("uuid", uuid).put("service", selected);
                case "write":
                    BluetoothSocket current = bluetooth;
                    if (current == null || !current.isConnected()) throw new IOException("No Bluetooth connection");
                    byte[] bytes = unhex(command.getString("hex"));
                    if (bytes.length == 0 || bytes.length > 65535) throw new IOException("Write length must be 1..65535 bytes");
                    try {
                        current.getOutputStream().write(bytes);
                        current.getOutputStream().flush();
                    } catch (IOException ex) {
                        disconnect();
                        throw ex;
                    }
                    return new JSONObject().put("written", bytes.length);
                case "disconnect":
                    disconnect();
                    return new JSONObject().put("connected", false);
                default:
                    throw new IOException("Unknown operation");
            }
        }

        private void readBluetooth(BluetoothSocket socket) {
            String reason = "remote EOF";
            try {
                InputStream stream = socket.getInputStream();
                byte[] buffer = new byte[4096];
                int count;
                while (!closed && (count = stream.read(buffer)) != -1) {
                    if (count == 0) continue;
                    send(new JSONObject().put("event", "data").put("hex", hex(buffer, count))
                        .put("elapsedRealtimeNanos", SystemClock.elapsedRealtimeNanos()));
                }
            } catch (Exception ex) { reason = ex.getMessage(); }
            if (bluetooth == socket) {
                disconnect();
                try { send(new JSONObject().put("event", "disconnected").put("reason", reason)); }
                catch (Exception ignored) { close(); }
                if (!closed) display("Glasses disconnected: " + reason);
            }
        }

        private void disconnect() {
            BluetoothSocket current = bluetooth;
            bluetooth = null;
            address = null;
            service = null;
            if (current != null) try { current.close(); } catch (IOException ignored) {}
        }

        @Override public void close() {
            closed = true;
            disconnect();
            timer.shutdownNow();
            try { client.close(); } catch (IOException ignored) {}
        }
    }

    private static String hex(byte[] data, int size) {
        final char[] digits = "0123456789abcdef".toCharArray();
        char[] chars = new char[size * 2];
        for (int i = 0; i < size; i++) {
            chars[2*i] = digits[(data[i] & 255) >>> 4];
            chars[2*i+1] = digits[data[i] & 15];
        }
        return new String(chars);
    }

    private static byte[] unhex(String value) throws IOException {
        if (value.length() % 2 != 0) throw new IOException("Odd hex length");
        byte[] bytes = new byte[value.length() / 2];
        for (int i = 0; i < bytes.length; i++) {
            int high = Character.digit(value.charAt(i*2), 16);
            int low = Character.digit(value.charAt(i*2+1), 16);
            if (high < 0 || low < 0) throw new IOException("Invalid hexadecimal byte");
            bytes[i] = (byte)((high << 4) | low);
        }
        return bytes;
    }
}
