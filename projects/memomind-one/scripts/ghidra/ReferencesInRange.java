import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.AddressSet;
import java.nio.file.*;
public class ReferencesInRange extends GhidraScript {
 public void run() throws Exception {
  var args=getScriptArgs(); var out=new StringBuilder();
  var iter=currentProgram.getReferenceManager().getReferenceDestinationIterator(new AddressSet(toAddr(args[1]),toAddr(args[2])),true);
  while(iter.hasNext()) {var a=iter.next();for(var r:getReferencesTo(a)){var f=getFunctionContaining(r.getFromAddress());if(f!=null)out.append(a).append(" FROM ").append(r.getFromAddress()).append(" FUNCTION ").append(f.getEntryPoint()).append(" TYPE ").append(r.getReferenceType()).append('\n');}}
  Files.writeString(Paths.get(args[0]),out.toString());
 }
}
