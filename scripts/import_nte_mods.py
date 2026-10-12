"""Import exported ZIPs without changing the export or existing IMM configs.

Each pak and its utoc/ucas companions form an independently selectable entry.
Archives with alternatives/components are split, never enabled together by default.
"""
import argparse
import hashlib
import json
import re
import shutil
import time
import zipfile
from pathlib import Path, PurePosixPath

MANAGED = "DISABLED - ALL MODS ARE STORED HERE (Managed by IMM)"
PAYLOAD = {".pak", ".utoc", ".ucas"}

def safe_name(name):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).rstrip(" .")[:140]

def run(export_root, source_root, config_path):
    index = json.loads((export_root / "export-index.json").read_text(encoding="utf-8-sig"))["mods"]
    by_name = {(m["object"], m["name"]): (key, m) for key, m in index.items()}
    library = source_root / MANAGED
    library.mkdir(parents=True, exist_ok=True)
    config = json.loads(Path("src/defaultXX.json").read_text(encoding="utf-8"))
    config.update(game="NTE", custom=1, sourceDir=str(source_root), targetDir=r"C:\Program Files\Neverness To Everness\Client\WindowsNoEditor\HT\Content\Paks\Mods")
    config["settings"].update(hotReload=0, nteLoader=str(source_root / "Loader/Mod注入器.exe"))
    categories = set()
    receipt = []
    skipped = []
    for archive in sorted((export_root / "Mods").rglob("*.zip")):
        category = safe_name(archive.parent.name)
        categories.add(category)
        key, metadata = by_name.get((archive.parent.name, archive.stem), ("", {}))
        with zipfile.ZipFile(archive) as z:
            infos = [i for i in z.infolist() if not i.is_dir()]
            # ZipFile checks each member's CRC while extracting.
            for entry in infos:
                parts = PurePosixPath(entry.filename.replace("\\", "/"))
                if parts.is_absolute() or ".." in parts.parts or any(":" in p for p in parts.parts):
                    raise ValueError(f"Unsafe archive entry: {archive}: {entry.filename}")
                if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError(f"Symlink archive member: {archive}: {entry.filename}")
            paks = [i for i in infos if PurePosixPath(i.filename).suffix.lower() == ".pak"]
            if not paks:
                skipped.append(str(archive))
                continue
            preview_candidates = [i for i in infos if PurePosixPath(i.filename).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
            for pak in paks:
                stem = str(PurePosixPath(pak.filename).with_suffix(""))
                suffix = "" if len(paks) == 1 else " · " + safe_name(PurePosixPath(stem).name)
                name = safe_name(archive.stem + suffix)
                dest = library / category / name
                if dest.exists():
                    raise ValueError(f"Import would overwrite: {dest}")
                dest.mkdir(parents=True)
                copied = []
                bundle = [i for i in infos if str(PurePosixPath(i.filename).with_suffix("")) == stem and PurePosixPath(i.filename).suffix.lower() in PAYLOAD]
                for entry in bundle:
                    filename = PurePosixPath(entry.filename).name
                    payload = dest / filename
                    with z.open(entry) as inp, payload.open("wb") as out:
                        shutil.copyfileobj(inp, out)
                    copied.append(dict(file=filename, bytes=entry.file_size, crc32=f"{entry.CRC:08x}"))
                # Keep documentation from the archive alongside each independent component.
                for entry in infos:
                    if PurePosixPath(entry.filename).suffix.lower() in {".txt", ".json", ".url", ".md"}:
                        doc = dest / "Documentation" / Path(*PurePosixPath(entry.filename).parts)
                        doc.parent.mkdir(parents=True, exist_ok=True)
                        doc.write_bytes(z.read(entry))
                preview_dir = export_root / "preview" / key
                external_previews = sorted(preview_dir.rglob("*")) if preview_dir.is_dir() else []
                external_previews = [p for p in external_previews if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
                if external_previews:
                    shutil.copyfile(external_previews[0], dest / ("preview" + external_previews[0].suffix))
                elif preview_candidates:
                    preview = next((i for i in preview_candidates if "preview" in i.filename.lower()), preview_candidates[0])
                    (dest / ("preview" + PurePosixPath(preview.filename).suffix)).write_bytes(z.read(preview))
                relative = str(Path(category) / name)
                note = metadata.get("explain", "")
                if len(paks) > 1:
                    note += f"\n原包包含 {len(paks)} 个 pak；此项仅为 {pak.filename}。按原包说明选择主文件和附件，互斥外观不要同时启用。"
                config["data"][relative] = dict(source=metadata.get("author", ""), note=note.strip(), tags=metadata.get("tags", []), addedAt=int(time.time()*1000))
                receipt.append(dict(archive=str(archive), mod=relative, files=copied))
        if len(receipt) % 20 == 0:
            print(f"Imported {len(receipt)} pak bundles", flush=True)
    for name in sorted(categories):
        config["settings"]["customCategories"][name] = {"_sIconUrl": "/who.jpg"}
    config["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    config["categories"] = json.loads(Path("src/gameData.json").read_text(encoding="utf-8"))["NTE"]["categoryList"]
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    (source_root / "import-receipt.json").write_text(json.dumps(dict(mods=receipt, skipped=skipped, enabled=[]), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Completed: {len(receipt)} pak bundles, {len(categories)} local categories, {len(skipped)} archives without pak. All disabled.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--export", type=Path, default=Path(r"F:\ntemods"))
    parser.add_argument("--source", type=Path, default=Path(r"F:\ntemod"))
    parser.add_argument("--config", type=Path, default=Path("acceptance/configNTE.json"))
    args = parser.parse_args()
    run(args.export, args.source, args.config)
