import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import com.google.gson.GsonBuilder;
import java.nio.file.*;
import java.util.*;

/** Read-only, bounded function/reference inventory; not a dead-code proof. */
public class DashboardInventory extends GhidraScript {
    public void run() throws Exception {
        String[] args=getScriptArgs();
        var start=toAddr(args[1]); var end=toAddr(args[2]);
        List<Map<String,Object>> rows=new ArrayList<>();
        var functions=currentProgram.getFunctionManager().getFunctions(start,true);
        while(functions.hasNext()) {
            Function f=functions.next();
            if(f.getEntryPoint().compareTo(end)>0)break;
            Map<String,Object> row=new LinkedHashMap<>();
            row.put("entry",f.getEntryPoint().toString());
            row.put("defined_body_bytes",f.getBody().getNumAddresses());
            List<String> ranges=new ArrayList<>();
            var rangeIter=f.getBody().getAddressRanges();
            while(rangeIter.hasNext()) {
                var range=rangeIter.next();
                ranges.add(range.getMinAddress()+".."+range.getMaxAddress());
            }
            row.put("body_ranges_inclusive",ranges);
            List<Map<String,Object>> incoming=new ArrayList<>();
            var addresses=f.getBody().getAddresses(true);
            while(addresses.hasNext()) {
                var at=addresses.next();
                for(var r:getReferencesTo(at)) {
                    if(f.getBody().contains(r.getFromAddress()))continue;
                    Function caller=getFunctionContaining(r.getFromAddress());
                    Map<String,Object> ref=new LinkedHashMap<>();
                    ref.put("from",r.getFromAddress().toString());ref.put("to",at.toString());
                    ref.put("type",r.getReferenceType().toString());
                    ref.put("containing_function",caller==null?null:caller.getEntryPoint().toString());
                    incoming.add(ref);
                }
            }
            row.put("known_incoming_references",incoming);
            List<String> callees=new ArrayList<>();
            for(Function callee:f.getCalledFunctions(monitor))callees.add(callee.getEntryPoint().toString());
            Collections.sort(callees);row.put("resolved_callees",callees);
            rows.add(row);
        }
        Map<String,Object> report=new LinkedHashMap<>();
        report.put("program",currentProgram.getName());
        report.put("input_sha256",currentProgram.getExecutableSHA256());
        report.put("entry_search_start",start.toString());report.put("entry_search_end_inclusive",end.toString());
        report.put("functions",rows);
        report.put("limitations",List.of("Defined function and resolved-reference coverage only; computed/unknown indirect references remain unresolved.","A function range is not a reclaimable region until live entry paths are replaced or removed.","No firmware or database mutation; no device execution."));
        Files.writeString(Paths.get(args[0]),new GsonBuilder().setPrettyPrinting().create().toJson(report));
    }
}
