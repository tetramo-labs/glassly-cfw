import ghidra.app.script.GhidraScript;
public class CreateSelectedFunctions extends GhidraScript {
 public void run() throws Exception {for(String s:getScriptArgs()){var a=toAddr(s);if(getFunctionAt(a)==null){if(getFunctionContaining(a)!=null)throw new IllegalStateException("Overlapping function "+s);disassemble(a);createFunction(a,null);}}}
}
