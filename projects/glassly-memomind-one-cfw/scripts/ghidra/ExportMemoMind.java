import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.Reference;
import com.google.gson.GsonBuilder;
import java.nio.file.*;
import java.util.*;
import java.util.regex.Pattern;

// Export focused static observations from an owned raw-image analysis project.
public class ExportMemoMind extends GhidraScript {
    @Override public void run() throws Exception {
        Path out = Paths.get(getScriptArgs()[0]);
        Files.createDirectories(out);
        Map<String,Object> report = new LinkedHashMap<>();
        report.put("program", currentProgram.getName());
        report.put("sha256", currentProgram.getExecutableSHA256());
        report.put("language", currentProgram.getLanguageID().getIdAsString());
        report.put("mapping_basis", "Segment3 header and partition metadata; startup address inferred, not executed");
        report.put("limitations", List.of("Raw RV32 decode and compiler convention are analyst-selected", "No RAM or peripheral mappings established", "Static references and decompilation do not prove runtime enforcement", "String and function coverage depends on Ghidra auto-analysis"));
        List<Map<String,Object>> memory = new ArrayList<>();
        for (var b : currentProgram.getMemory().getBlocks()) {
            Map<String,Object> row = new LinkedHashMap<>();
            row.put("name", b.getName()); row.put("start", b.getStart().toString());
            row.put("end_inclusive", b.getEnd().toString()); row.put("size", b.getSize());
            memory.add(row);
        }
        report.put("memory", memory);
        List<Map<String,Object>> strings = new ArrayList<>();
        LinkedHashSet<Function> selected = new LinkedHashSet<>();
        Function startup = getFunctionAt(toAddr("041eb020"));
        if (startup != null) selected.add(startup);
        Pattern pattern = Pattern.compile("(?i)(ota|firmware|upgrad|verif|signatur|checksum|md5|crc|plugin|native.app|capabil)");
        DataIterator definedData = currentProgram.getListing().getDefinedData(true);
        while (definedData.hasNext()) {
            Data d = definedData.next();
            Object value = d.getValue();
            if (!(value instanceof String) || !pattern.matcher((String)value).find()) continue;
            Map<String,Object> row = new LinkedHashMap<>();
            row.put("address", d.getAddress().toString()); row.put("text", value);
            List<Map<String,String>> refs = new ArrayList<>();
            for (Reference r : getReferencesTo(d.getAddress())) {
                Map<String,String> ref = new LinkedHashMap<>();
                ref.put("from", r.getFromAddress().toString()); ref.put("type", r.getReferenceType().toString());
                Function f = getFunctionContaining(r.getFromAddress());
                if (f != null) { ref.put("function", f.getEntryPoint().toString()); selected.add(f); }
                refs.add(ref);
            }
            row.put("references", refs); strings.add(row);
        }
        report.put("matching_defined_strings", strings);
        report.put("total_function_count", currentProgram.getFunctionManager().getFunctionCount());
        List<Map<String,Object>> functions = new ArrayList<>();
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try {
            int count = 0;
            for (Function f : selected) {
                if (count++ >= 100) break;
                Map<String,Object> row = new LinkedHashMap<>();
                row.put("address", f.getEntryPoint().toString()); row.put("name", f.getName());
                row.put("body_address_count", f.getBody().getNumAddresses());
                List<String> callers = new ArrayList<>();
                for (Reference ref : getReferencesTo(f.getEntryPoint()))
                    callers.add(ref.getFromAddress()+" "+ref.getReferenceType());
                row.put("incoming_references", callers);
                DecompileResults result = decompiler.decompileFunction(f, 30, monitor);
                row.put("decompile_completed", result.decompileCompleted());
                row.put("error", result.getErrorMessage());
                if (result.decompileCompleted() && result.getDecompiledFunction()!=null) {
                    String filename = "function-"+f.getEntryPoint()+".c";
                    Files.writeString(out.resolve(filename), result.getDecompiledFunction().getC());
                    row.put("decompiled_file", filename);
                }
                StringBuilder assembly = new StringBuilder();
                var instructions = currentProgram.getListing().getInstructions(f.getBody(), true);
                while (instructions.hasNext()) { var i = instructions.next(); assembly.append(i.getAddress()).append("  ").append(i).append('\n'); }
                String asmName = "function-"+f.getEntryPoint()+".asm";
                Files.writeString(out.resolve(asmName), assembly.toString()); row.put("assembly_file", asmName);
                functions.add(row);
            }
        } finally { decompiler.dispose(); }
        report.put("selected_function_count", selected.size()); report.put("exported_functions", functions);
        Files.writeString(out.resolve("report.json"),new GsonBuilder().setPrettyPrinting().create().toJson(report));
        println("MemoMind export: "+strings.size()+" matching strings, "+functions.size()+" functions; total functions "+currentProgram.getFunctionManager().getFunctionCount());
    }
}
