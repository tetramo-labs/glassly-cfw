import org.memomind.research.hid.ControllerLease;
public final class ControllerLeaseTest {
 static int checks;
 static void check(boolean value){checks++;if(!value)throw new AssertionError("lease check "+checks);}
 static void fails(Runnable r){boolean failed=false;try{r.run();}catch(IllegalStateException e){failed=true;}check(failed);}
 public static void main(String[] args){
  long base=123456789L;
  ControllerLease waiting=new ControllerLease(base);
  check(!waiting.authenticated());check(waiting.remaining(base)==120000);
  fails(()->waiting.request(base+1));check(waiting.remaining(base+1)==119999);
  check(!waiting.expired(base+119999));check(waiting.expired(base+120000));
  fails(()->waiting.authenticate(base+120000));check(waiting.remaining(base+120001)==0);
  ControllerLease active=new ControllerLease(base);
  active.authenticate(base+119999);long auth=base+119999,hard=auth+600000;
  check(active.authenticated());check(active.hardDeadline()==hard);
  fails(()->active.authenticate(auth+1));check(active.hardDeadline()==hard);
  // Regular requests keep the socket idle lease alive, never extend the hard lease.
  for(long now=auth;now<hard;now+=1000){active.request(now);check(!active.expired(now));check(active.hardDeadline()==hard);check(active.remaining(now)<=120000&&active.remaining(now)<=hard-now);}
  check(active.expired(hard));fails(()->active.request(hard));check(active.remaining(hard)==0);
  ControllerLease idle=new ControllerLease(0);idle.authenticate(0);idle.request(10000);
  check(!idle.expired(129999));check(idle.expired(130000));fails(()->idle.request(130000));
  ControllerLease stopped=new ControllerLease(0);stopped.authenticate(1);stopped.stop();
  check(stopped.expired(1));check(stopped.remaining(1)==0);fails(()->stopped.request(2));fails(()->stopped.authenticate(2));
  // Reopening/foregrounding the UI does not instantiate a new service lease;
  // this existing object remains unchanged while time advances without commands.
  ControllerLease original=new ControllerLease(0);original.authenticate(10);
  long originalHard=original.hardDeadline();check(!original.expired(110000));check(original.hardDeadline()==originalHard);
  check(original.expired(120010));
  // elapsedRealtime is a64-bit clock; operation beyond32-bit wrap is preserved.
  ControllerLease longUptime=new ControllerLease(0x100000000L);longUptime.authenticate(0x100000001L);
  check(!longUptime.expired(0x100000002L));check(longUptime.hardDeadline()==0x100000001L+600000);
  System.out.println("lifecycle_checks="+checks);
 }
}
