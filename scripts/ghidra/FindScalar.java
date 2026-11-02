import ghidra.app.script.GhidraScript;
import ghidra.program.model.scalar.Scalar;
import java.nio.file.*;
public class FindScalar extends GhidraScript {
 public void run() throws Exception {
  var args=getScriptArgs();long value=Long.decode(args[1]);var out=new StringBuilder();
  var iter=currentProgram.getListing().getInstructions(true);
  while(iter.hasNext()) {var ins=iter.next();boolean match=false;for(int n=0;n<ins.getNumOperands();n++)for(var op:ins.getOpObjects(n))if(op instanceof Scalar && ((Scalar)op).getUnsignedValue()==value)match=true;
  if(!match)continue;var f=getFunctionContaining(ins.getAddress());if(f==null)continue;
  out.append("MATCH ").append(ins.getAddress()).append(" FUNCTION ").append(f.getEntryPoint()).append('\n');var i=ins;
  for(int n=0;n<3&&i.getPrevious()!=null;n++)i=i.getPrevious();for(int n=0;n<8&&i!=null;n++,i=i.getNext())out.append(i.getAddress()).append("  ").append(i).append('\n');}
  Files.writeString(Paths.get(args[0]),out.toString());
 }
}
