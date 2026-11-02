import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;

// Source-derived mapping, not a runtime observation. No executable bytes change.
public class SeedMemoMind extends GhidraScript {
    @Override public void run() throws Exception {
        if (!currentProgram.getLanguageID().getIdAsString().equals("RISCV:LE:32:default"))
            throw new IllegalStateException("Expected explicit RV32 little-endian import");
        Address entry = toAddr("041eb020");
        if (!currentProgram.getMemory().getMinAddress().equals(entry))
            throw new IllegalStateException("Unexpected app mapping");
        addEntryPoint(entry);
        if (!disassemble(entry)) throw new IllegalStateException("Entry decode failed");
        createFunction(entry, "candidate_startup");
    }
}
