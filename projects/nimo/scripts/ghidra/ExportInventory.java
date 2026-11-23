import ghidra.app.script.GhidraScript;
import ghidra.program.model.data.StringDataInstance;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.Reference;
import java.nio.file.*;
import java.util.*;

// functions.tsv: entry, size, caller count, callee count, name
// strings.tsv:   address, referencing functions (entry), text
// Analysis output only.
public class ExportInventory extends GhidraScript {
    @Override public void run() throws Exception {
        Path out = Paths.get(getScriptArgs()[0]);
        Files.createDirectories(out);
        var listing = currentProgram.getListing();
        var fm = currentProgram.getFunctionManager();
        StringBuilder fn = new StringBuilder();
        for (Function f : fm.getFunctions(true)) {
            int callers = f.getCallingFunctions(monitor).size();
            int callees = f.getCalledFunctions(monitor).size();
            fn.append(f.getEntryPoint()).append('\t').append(f.getBody().getNumAddresses()).append('\t')
              .append(callers).append('\t').append(callees).append('\t').append(f.getName()).append('\n');
        }
        Files.writeString(out.resolve("functions.tsv"), fn.toString());
        StringBuilder st = new StringBuilder();
        for (Data d : listing.getDefinedData(true)) {
            if (!d.hasStringValue()) continue;
            String text = StringDataInstance.getStringDataInstance(d).getStringValue();
            if (text == null || text.length() < 3) continue;
            Set<String> users = new TreeSet<>();
            for (Reference r : getReferencesTo(d.getAddress())) {
                Function f = fm.getFunctionContaining(r.getFromAddress());
                users.add(f == null ? "?" + r.getFromAddress() : f.getEntryPoint().toString());
            }
            st.append(d.getAddress()).append('\t').append(String.join(",", users)).append('\t')
              .append(text.replace("\n", "\\n").replace("\t", "\\t")).append('\n');
        }
        Files.writeString(out.resolve("strings.tsv"), st.toString());
        println("exported " + fm.getFunctionCount() + " functions");
    }
}
