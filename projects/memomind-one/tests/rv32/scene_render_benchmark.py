#!/usr/bin/env python3
"""Instruction profile of phone-captured scene commands on the linked RV32 runtime.

Replays the commands a MemoMind renderer produced (JSON: [{name, commands:[hex]}])
through the real display job and attributes every instruction to the runtime
function it executed in. Animation ticks after a tween are profiled the same
way. Native fonts, flash and LVGL are the existing explicit mocks, so native
font lookups and the physical panel cost zero instructions here: this measures
the runtime's own work, offline, for comparing builds. It is not a time claim.
"""
import argparse, bisect, collections, json, struct
from pathlib import Path
import graphics_runtime_emulator_test as G
import scene_runtime_emulator_test as S
import minimal_owner_flash_runtime_emulator_test as M

GLYPH_W, GLYPH_H, GLYPH_BPP, ADVANCE = 16, 26, 2, 18


class BenchMachine(M.FlashMachine):
    instruction_budget = 4_000_000_000

    def __init__(self):
        super().__init__()
        symbols = []
        for line in (G.BUILD / "graphics.symbols.txt").read_text().splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[1] in "tT":
                symbols.append((int(parts[0], 16), parts[2]))
        symbols.sort()
        self.symbol_addresses = [a for a, _ in symbols]
        self.symbol_names = [n for _, n in symbols]
        self.symbol_starts = {a: n for a, n in symbols}
        self.profile = collections.Counter()
        self.call_edges = collections.Counter()  # (caller, callee) -> entries, by block start at a symbol
        self.last_symbol = "?"
        # A 34 px native font whose glyphs are 16x26 at 4 bpp, like the stock
        # resource font the dashboard text is drawn with on the glasses.
        self.uc.mem_write(S.FONT, struct.pack("<IIiiI", 0, 0, 34, 8, 0))
        pattern = bytes((0xF0 if (i // 8) % 2 else 0x0F) for i in range(GLYPH_W * GLYPH_H * GLYPH_BPP // 8 + 8))
        self.glyph_bits = self.allocate(len(pattern), "mock-glyph-bits", pattern, writable=False)

    def instruction(self, uc, address, size, userdata):
        i = bisect.bisect_right(self.symbol_addresses, address) - 1
        name = self.symbol_names[i] if i >= 0 else "?"
        self.profile[name] += 1
        callee = self.symbol_starts.get(address)
        if callee is not None and self.last_symbol != callee:
            self.call_edges[(self.last_symbol, callee)] += 1
        self.last_symbol = name
        return super().instruction(uc, address, size, userdata)

    def native(self, name, args):
        if name == "font_metrics":
            font, glyph, cp, following = args[:4]
            assert font == S.FONT
            self.native_write(glyph, struct.pack("<IHHHhhBB", font, ADVANCE, GLYPH_W, GLYPH_H, 1, 0, GLYPH_BPP, 0))
            return 1
        if name == "font_bitmap":
            assert args[0] == S.FONT
            return self.glyph_bits
        return super().native(name, args)

    def canvas(self):
        pixels = self.image_sources[-1][4]
        return self.read(pixels + 64, 300 * 350)


def profile_step(machine, label, run):
    before = machine.profile.copy()
    calls_before = machine.call_edges.copy()
    total = machine.instructions
    run()
    delta = machine.profile - before
    count = machine.instructions - total
    top = [{"function": f, "instructions": n, "share": round(n / count, 3)} for f, n in delta.most_common(12)]
    calls = [{"caller": a, "callee": b, "entries": n} for (a, b), n in (machine.call_edges - calls_before).most_common(24)]
    return {"step": label, "instructions": count, "top": top, "calls": calls}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--commands", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--ticks", type=int, default=4, help="Animation ticks to profile after the last tween")
    parser.add_argument("--canvas", type=Path, help="Write the final canvas as a PGM for a visual check")
    parser.add_argument("--calls", type=int, default=0, help="Also print the N most frequent caller -> callee entries per step")
    args = parser.parse_args()
    G.BUILD = args.build.resolve()
    build = json.loads((G.BUILD / "build.json").read_text())
    G.PINNED_SHA = build["blob_sha256"]
    machine = BenchMachine()
    frames = json.loads(args.commands.read_text())
    steps = []
    for frame in frames:
        for index, command in enumerate(frame["commands"]):
            data = bytes.fromhex(command)
            label = f"{frame['name']}[{index}] mode {data[0]} ({len(data)} B)"
            replies = {}

            def run():
                reply, values = machine.send_scene(data)
                replies["status"] = reply[3] if reply else None
                replies["result"] = [v.get("result") for v in values]
            step = profile_step(machine, label, run)
            step.update(replies)
            steps.append(step)
            assert replies["status"] in (0, 5, None), (label, replies)
    period = 33
    for tick in range(args.ticks):
        machine.now += period
        timer = next(iter(machine.timers))
        steps.append(profile_step(machine, f"tick {tick + 1} (+{period} ms)", lambda: machine.call("tick", timer, display=True)))
    if args.canvas:
        raw = machine.canvas()
        rows = []
        for y in range(350):
            row = raw[y * 300:(y + 1) * 300]
            rows.append(bytes(v for b in row for v in ((b >> 4) * 17, (b & 15) * 17)))
        args.canvas.write_bytes(b"P5\n600 350\n255\n" + b"".join(rows))
    report = {"build": str(G.BUILD), "blob_sha256": build["blob_sha256"], "cfw_revision": build.get("cfw_revision"),
              "commands": str(args.commands), "steps": steps}
    args.report.write_text(json.dumps(report, indent=1))
    for step in steps:
        print(f"{step['instructions']:>12,}  {step['step']}")
        for t in step["top"][:5]:
            print(f"               {t['share']:5.1%} {t['function']}")
        if args.calls:
            for c in step["calls"][:args.calls]:
                print(f"               {c['entries']:>7} {c['caller']} -> {c['callee']}")


if __name__ == "__main__":
    main()
