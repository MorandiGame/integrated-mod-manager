"""Static x64 cross references and function bodies; no binary is executed."""
import bisect
import json
import re
from pathlib import Path
import capstone
import pefile

ROOT = Path(r"F:\ntemod\Loader\Mod Loader")
OUT = Path("tools/loader-analysis")
NEEDLES = re.compile(r"CBTProc|HTGame|MyCustomLoader|\.asi|plugins|SigBypass|config\.ini|Signature|signature|[Bb]ypass|Launcher|Target|DllName|Nt[A-Z]|Ldr[A-Z]")
APIS = {"SetWindowsHookExW", "UnhookWindowsHookEx", "LoadLibraryExW", "LoadLibraryExA", "LoadLibraryW", "LoadLibraryA", "GetProcAddress", "CreateThread", "VirtualProtect", "FlushInstructionCache", "K32GetModuleInformation", "GetModuleHandleA", "GetModuleFileNameW", "GetModuleFileNameA", "FindFirstFileW", "FindNextFileW", "PostThreadMessageW", "EnumWindows", "GetWindowThreadProcessId", "CallNextHookEx", "GetPrivateProfileStringW", "GetPrivateProfileStringA", "ShellExecuteW"}

for file in [ROOT / "Game start.exe", ROOT / "MyCustomLoader.dll", ROOT / "plugins/UniversalSigBypasser.asi"]:
    raw = file.read_bytes()
    pe = pefile.PE(data=raw)
    base = pe.OPTIONAL_HEADER.ImageBase
    image = pe.get_memory_mapped_image()
    imports = {i.address: i.name.decode() for d in pe.DIRECTORY_ENTRY_IMPORT for i in d.imports if i.name}
    functions = sorted((base + x.struct.BeginAddress, base + x.struct.EndAddress) for x in pe.DIRECTORY_ENTRY_EXCEPTION)
    starts = [s for s, _ in functions]
    strings = {}
    for match in re.finditer(rb"[\x20-\x7e]{4,}\x00", image):
        value = match.group()[:-1].decode()
        if NEEDLES.search(value): strings[base+match.start()] = value
    for match in re.finditer(rb"(?:[\x20-\x7e]\x00){4,}\x00\x00", image):
        value = match.group()[:-2].decode("utf-16le")
        if NEEDLES.search(value): strings[base+match.start()] = value
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    def annotations(ins):
        result = []
        for op in ins.operands:
            if op.type == capstone.CS_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                address = ins.address + ins.size + op.mem.disp
                if address in imports: result.append(imports[address])
                if address in strings: result.append(repr(strings[address]))
            if op.type == capstone.CS_OP_IMM and op.imm in strings:
                result.append(repr(strings[op.imm]))
        return result
    selected = []
    for start, end in functions:
        instructions = list(md.disasm(image[start-base:end-base], start))
        if any(any(a in APIS or NEEDLES.search(a) for a in annotations(ins)) for ins in instructions):
            selected.append((start, end, instructions))
    stream = []
    for start, end, instructions in selected:
        stream.append(f"\nFUNCTION {start:#x} .. {end:#x}")
        for ins in instructions:
            stream.append(f"{ins.address:016x}  {ins.mnemonic:9} {ins.op_str:50} {' ; '.join(annotations(ins))}")
    (OUT / (file.name + ".xrefs.txt")).write_text("\n".join(stream), encoding="utf-8")
    print(f"{file.name}: {len(selected)} referenced functions")
