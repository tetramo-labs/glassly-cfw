import ghidra.app.script.GhidraScript;
import java.nio.file.*;
public class RefsTo extends GhidraScript {
 public void run() throws Exception {
  var args=getScriptArgs();var out=new StringBuilder();
  for(int n=1;n<args.length;n++){
   out.append("== ").append(args[n]).append('\n');
   for(var r:getReferencesTo(toAddr(args[n]))){var f=getFunctionContaining(r.getFromAddress());
    out.append(r.getFromAddress()).append(' ').append(r.getReferenceType()).append(' ').append(f==null?"-":f.getEntryPoint().toString()).append('\n');}
  }
  Files.writeString(Paths.get(args[0]),out.toString());
 }
}
