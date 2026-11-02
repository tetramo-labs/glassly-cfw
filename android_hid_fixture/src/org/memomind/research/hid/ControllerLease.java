package org.memomind.research.hid;

/** Monotonic-clock policy actually enforced by HidService, independent of Android. */
public final class ControllerLease {
    public static final long WAIT_MS=120000, IDLE_MS=120000, SESSION_MS=600000;
    private long idleDeadline, hardDeadline;
    private boolean authenticated, stopped;
    public ControllerLease(long now){idleDeadline=now+WAIT_MS;hardDeadline=idleDeadline;}
    public void authenticate(long now){
        requireAlive(now);
        if(authenticated)throw new IllegalStateException("already authenticated");
        authenticated=true;idleDeadline=now+IDLE_MS;hardDeadline=now+SESSION_MS;
    }
    public void request(long now){
        requireAlive(now);if(!authenticated)throw new IllegalStateException("authenticate first");
        idleDeadline=Math.min(now+IDLE_MS,hardDeadline);
    }
    public boolean expired(long now){return stopped||now>=idleDeadline||now>=hardDeadline;}
    public long remaining(long now){return stopped?0:Math.max(0,Math.min(idleDeadline,hardDeadline)-now);}
    public long hardDeadline(){return hardDeadline;}
    public boolean authenticated(){return authenticated;}
    public void stop(){stopped=true;}
    private void requireAlive(long now){if(expired(now))throw new IllegalStateException("controller lease expired");}
}
