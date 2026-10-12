"""Read-only loader evidence extraction. Never executes the inspected binaries."""
import hashlib
import io
import json
import re
import struct
from pathlib import Path

import pefile
from PyInstaller.archive.readers import CArchiveReader
from xdis.disasm import disassemble_file

ROOT = Path(r"C:\Program Files\Neverness To Everness\Client\WindowsNoEditor\HT\Content\Paks\Mods")
OUT = Path("tools/loader-analysis")
OUT.mkdir(parents=True, exist_ok=True)
records = []
for file in [ROOT / "Mod注入器.exe", *(ROOT / "Mod Loader").rglob("*.exe"), *(ROOT / "Mod Loader").rglob("*.dll"), *(ROOT / "Mod Loader").rglob("*.asi")]:
    raw = file.read_bytes()
    pe = pefile.PE(data=raw)
    strings = sorted(set(x.decode("ascii") for x in re.findall(rb"[\x20-\x7e]{5,}", raw)))
    strings += sorted(set(x.decode("utf-16le") for x in re.findall(rb"(?:[\x20-\x7e]\x00){5,}", raw)))
    (OUT / (file.name + ".strings.txt")).write_text("\n".join(strings), encoding="utf-8")
    imports = {i.dll.decode(): [f.name.decode() if f.name else f"ordinal:{f.ordinal}" for f in i.imports] for i in getattr(pe, "DIRECTORY_ENTRY_IMPORT", [])}
    exports = [e.name.decode() if e.name else str(e.ordinal) for e in getattr(getattr(pe, "DIRECTORY_ENTRY_EXPORT", None), "symbols", [])]
    records.append(dict(file=str(file), size=len(raw), sha256=hashlib.sha256(raw).hexdigest(), machine=hex(pe.FILE_HEADER.Machine), imports=imports, exports=exports, image_base=hex(pe.OPTIONAL_HEADER.ImageBase)))
    if file.name == "Mod注入器.exe":
        archive = CArchiveReader(str(file))
        pyz = archive.extract("PYZ.pyz")
        magic = pyz[4:8]
        for name, entry in archive.toc.items():
            if entry[-1] == "s" and not name.startswith(("pyi", "struct")):
                bytecode = archive.extract(name)
                pyc = OUT / "injector.pyc"
                pyc.write_bytes(magic + struct.pack("<III", 0, 0, 0) + bytecode)
                stream = io.StringIO()
                disassemble_file(str(pyc), outstream=stream)
                (OUT / "injector.disassembly.txt").write_text(stream.getvalue(), encoding="utf-8")
(OUT / "pe-evidence.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Evidence written to {OUT.resolve()} ({len(records)} binaries)")
