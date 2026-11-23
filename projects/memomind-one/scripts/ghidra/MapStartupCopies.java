import ghidra.app.script.GhidraScript;
import java.math.BigInteger;

// Mapping is derived from instructions at 041fb1ec and gp setup at 041eb03e.
// These are analysis memory blocks; no input or device bytes are changed.
public class MapStartupCopies extends GhidraScript {
    @Override public void run() throws Exception {
        var memory=currentProgram.getMemory();
        var source=memory.getAllFileBytes().get(0);
        if(memory.getBlock("startup_ram_code")==null){
            var code=memory.createInitializedBlock("startup_ram_code",toAddr("02000000"),source,0x64,0xf8b4,false);
            code.setRead(true);code.setWrite(true);code.setExecute(true);
            code.setComment("Startup041fb1ec copies file+0x64/XIP041eb084 to02000000..0200f8b4 exclusive");
            var data=memory.createInitializedBlock("startup_ram_data",toAddr("0200f8b8"),source,0x4399fc8L-0x41eb020L,0x1e78,false);
            data.setRead(true);data.setWrite(true);data.setExecute(false);
            data.setComment("Startup041fb210 copies04399fc8 to0200f8b8..02011730 exclusive with gp02011688");
            var bss=memory.createUninitializedBlock("startup_bss",toAddr("02011878"),0x205e128L-0x2011878L,false);
            bss.setRead(true);bss.setWrite(true);bss.setExecute(false);
            bss.setComment("Startup041fb234 zeroes02011878..0205e128 exclusive; modeled uninitialized to avoid inventing runtime state");
        }
        var gp=currentProgram.getRegister("gp");
        for(var block:memory.getBlocks())currentProgram.getProgramContext().setValue(gp,block.getStart(),block.getEnd(),new BigInteger("02011688",16));
        for(String s:new String[]{"02000000","020000da","02003d9c","02009904","020099a0","0200b23e","0200b400","0200a008","0200a264"}){
            var a=toAddr(s);disassemble(a);if(getFunctionAt(a)==null)createFunction(a,null);
        }
        analyzeAll(currentProgram);
        println("Mapped startup copies and gp; analysis-derived only");
    }
}
