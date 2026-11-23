import ghidra.app.script.GhidraScript;
import java.math.BigInteger;

// NIMO 1.1.5.1 app image (XIP load 041b4020). Derived from the startup code:
// gp/sp set at 041b403e, init at 041c3b4e copies file+0x64 (XIP 041b4084) to
// 02000000..0200fa3c, copies 04415898 to 0200fa40..gp+4, and zeroes gp+176..0209be74.
// Analysis memory blocks only; no image or device bytes change.
public class MapStartupCopies extends GhidraScript {
    @Override public void run() throws Exception {
        var memory = currentProgram.getMemory();
        var source = memory.getAllFileBytes().get(0);
        if (memory.getBlock("startup_ram_code") == null) {
            var code = memory.createInitializedBlock("startup_ram_code", toAddr("02000000"), source, 0x64, 0xfa3c, false);
            code.setRead(true); code.setWrite(true); code.setExecute(true);
            code.setComment("041c3b4e copies XIP 041b4084 to 02000000..0200fa3c exclusive");
            var data = memory.createInitializedBlock("startup_ram_data", toAddr("0200fa40"), source, 0x4415898L - 0x41b4020L, 0x20e4, false);
            data.setRead(true); data.setWrite(true); data.setExecute(false);
            data.setComment("041c3b8e copies 04415898 to 0200fa40..02011b24 exclusive (gp 02011b20)");
            var bss = memory.createUninitializedBlock("startup_bss", toAddr("02011bd0"), 0x209be74L - 0x2011bd0L, false);
            bss.setRead(true); bss.setWrite(true); bss.setExecute(false);
            bss.setComment("041c3bac zeroes 02011bd0..0209be74 exclusive; uninitialized here");
        }
        var gp = currentProgram.getRegister("gp");
        for (var block : memory.getBlocks())
            currentProgram.getProgramContext().setValue(gp, block.getStart(), block.getEnd(), new BigInteger("02011b20", 16));
        for (String s : new String[] {"041b4020", "041c3b4e", "041c3be0", "042fe002", "02000000", "020000da", "0200a200"}) {
            var a = toAddr(s);
            disassemble(a);
            if (getFunctionAt(a) == null) createFunction(a, null);
        }
        analyzeAll(currentProgram);
        println("Mapped NIMO startup copies and gp");
    }
}
