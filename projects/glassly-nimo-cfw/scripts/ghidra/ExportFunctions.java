import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.Reference;
import com.google.gson.GsonBuilder;
import java.nio.file.*;
import java.util.*;

public class ExportFunctions extends GhidraScript {
    @Override public void run() throws Exception {
        String[] args=getScriptArgs(); Path out=Paths.get(args[0]); Files.createDirectories(out);
        List<Map<String,Object>> rows=new ArrayList<>();
        DecompInterface dec=new DecompInterface(); dec.openProgram(currentProgram);
        try { for(int n=1;n<args.length;n++) {
            var addr=toAddr(args[n]); Function f=getFunctionAt(addr);
            Map<String,Object> row=new LinkedHashMap<>(); row.put("requested",args[n]);
            if(f==null) {row.put("error","No function at selected address");rows.add(row);continue;}
            row.put("address",f.getEntryPoint().toString());
            List<String> refs=new ArrayList<>(); for(Reference r:getReferencesTo(f.getEntryPoint()))refs.add(r.getFromAddress()+" "+r.getReferenceType());
            row.put("incoming_references",refs);
            DecompileResults result=dec.decompileFunction(f,60,monitor);row.put("completed",result.decompileCompleted());row.put("error",result.getErrorMessage());
            String stem="function-"+args[n];
            if(result.decompileCompleted()&&result.getDecompiledFunction()!=null)Files.writeString(out.resolve(stem+".c"),result.getDecompiledFunction().getC());
            StringBuilder asm=new StringBuilder();var instructions=currentProgram.getListing().getInstructions(f.getBody(),true);
            while(instructions.hasNext()){var i=instructions.next();asm.append(i.getAddress()).append("  ").append(i).append('\n');}
            Files.writeString(out.resolve(stem+".asm"),asm.toString());rows.add(row);
        }}finally{dec.dispose();}
        Files.writeString(out.resolve("functions.json"),new GsonBuilder().setPrettyPrinting().create().toJson(rows));
    }
}
