import ghidra.app.script.GhidraScript;
import java.nio.file.*;
public class CallSites extends GhidraScript {
 public void run() throws Exception {
  var args=getScriptArgs();var out=new StringBuilder();
  for(var r:getReferencesTo(toAddr(args[1]))) {
   var f=getFunctionContaining(r.getFromAddress()); if(f==null)continue;
   out.append("CALL ").append(r.getFromAddress()).append(" FUNCTION ").append(f.getEntryPoint()).append('\n');
   var i=getInstructionAt(r.getFromAddress()); if(i==null)continue;
   for(int n=0;n<10 && i.getPrevious()!=null;n++)i=i.getPrevious();
   for(int n=0;n<15 && i!=null;n++,i=i.getNext())out.append(i.getAddress()).append("  ").append(i).append('\n');
  }
  Files.writeString(Paths.get(args[0]),out.toString());
 }
}
