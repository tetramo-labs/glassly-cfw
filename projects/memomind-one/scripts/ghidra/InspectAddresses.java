import ghidra.app.script.GhidraScript;
import java.nio.file.*;
public class InspectAddresses extends GhidraScript {
    @Override public void run() throws Exception {
        String[] args=getScriptArgs();StringBuilder s=new StringBuilder();
        for(int n=1;n<args.length;n++){
            var a=toAddr(args[n]);s.append("ADDRESS ").append(a).append('\n');
            var f=getFunctionContaining(a);s.append("FUNCTION ").append(f==null?"none":f.getEntryPoint()).append('\n');
            for(var r:getReferencesTo(a)){
                var caller=getFunctionContaining(r.getFromAddress());s.append("REF ").append(r.getFromAddress()).append(' ').append(r.getReferenceType()).append(" FUNCTION ").append(caller==null?"none":caller.getEntryPoint()).append('\n');
            }
            var i=getInstructionContaining(a);s.append("INSTRUCTION ").append(i).append('\n');
        }
        Files.writeString(Paths.get(args[0]),s.toString());
    }
}
