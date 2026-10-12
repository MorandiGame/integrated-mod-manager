//! NTE stores its library outside the game. Only owned directory links are activated.
use serde::Serialize;
use std::fs;
use std::path::{Component, Path, PathBuf};

const SOURCE: &str = "DISABLED - ALL MODS ARE STORED HERE (Managed by IMM)";
const TARGET: &str = "DO NOT MODIFY (Managed by IMM)";

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PakMod {
    path: String,
    name: String,
    parent: String,
    enabled: bool,
    pak_count: usize,
}

fn is_link(meta: &fs::Metadata) -> bool {
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        meta.file_attributes() & 0x400 != 0
    }
    #[cfg(not(windows))]
    { meta.file_type().is_symlink() }
}

fn relative_mod(path: &str) -> Result<PathBuf, String> {
    // Both separators are accepted, but only category/mod is allowed.
    let parts: Vec<_> = path.split(['/', '\\']).collect();
    if parts.len() != 2 || parts.iter().any(|p| p.is_empty() || *p == "." || *p == ".." || p.contains(':')) {
        return Err("Expected a relative category/mod path".into());
    }
    let result: PathBuf = parts.iter().collect();
    if result.components().any(|p| !matches!(p, Component::Normal(_))) {
        return Err("Invalid mod path".into());
    }
    Ok(result)
}

fn roots(source: &str, target: &str) -> Result<(PathBuf, PathBuf), String> {
    let src = fs::canonicalize(source).map_err(|e| format!("Library: {e}"))?;
    let tgt = fs::canonicalize(target).map_err(|e| format!("Game Mods directory: {e}"))?;
    if !src.is_dir() || !tgt.is_dir() || src.starts_with(&tgt) || tgt.starts_with(&src) {
        return Err("NTE library must be outside the game's Mods directory".into());
    }
    if !tgt.file_name().is_some_and(|n| n.eq_ignore_ascii_case("Mods"))
        || !tgt.parent().and_then(Path::file_name).is_some_and(|n| n.eq_ignore_ascii_case("Paks")) {
        return Err("NTE target must be the game's Paks/Mods directory".into());
    }
    // Do not accept an external source anywhere inside the same Content/Paks tree.
    if src.starts_with(tgt.parent().unwrap()) {
        return Err("NTE library cannot be stored inside Paks".into());
    }
    Ok((src, tgt))
}

fn plain_directory(path: &Path, create: bool) -> Result<(), String> {
    if create && !path.exists() { fs::create_dir(path).map_err(|e| e.to_string())?; }
    let meta = fs::symlink_metadata(path).map_err(|e| e.to_string())?;
    if !meta.is_dir() || is_link(&meta) { return Err(format!("Refusing redirected directory: {}", path.display())); }
    Ok(())
}

fn pak_count(path: &Path) -> Result<usize, String> {
    let mut count = 0;
    for entry in fs::read_dir(path).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let meta = fs::symlink_metadata(entry.path()).map_err(|e| e.to_string())?;
        // Never follow reparse points from a downloaded mod.
        if is_link(&meta) { return Err("Mod contains a symbolic link or junction".into()); }
        if meta.is_dir() { count += pak_count(&entry.path())?; }
        else if entry.path().extension().is_some_and(|e| e.eq_ignore_ascii_case("pak")) { count += 1; }
    }
    Ok(count)
}

fn owned_link(link: &Path, expected: &Path) -> Result<bool, String> {
    match fs::symlink_metadata(link) {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(false),
        Err(e) => Err(e.to_string()),
        Ok(meta) => {
            if !is_link(&meta) { return Err(format!("Refusing to modify an ordinary directory/file: {}", link.display())); }
            let resolved = fs::canonicalize(link).map_err(|e| format!("Cannot verify link ownership: {e}"))?;
            let expected = fs::canonicalize(expected).map_err(|e| e.to_string())?;
            if resolved != expected { return Err(format!("Link points to another mod: {}", link.display())); }
            Ok(true)
        }
    }
}

#[tauri::command]
pub fn nte_prepare_storage(source_dir: String, target_dir: String) -> Result<(), String> {
    let (src, _) = roots(&source_dir, &target_dir)?;
    plain_directory(&src.join(SOURCE), true)
}

#[tauri::command]
pub fn nte_list_mods(source_dir: String, target_dir: String) -> Result<Vec<PakMod>, String> {
    let (src, tgt) = roots(&source_dir, &target_dir)?;
    let library = src.join(SOURCE);
    plain_directory(&library, false)?;
    let mut result = Vec::new();
    for category in fs::read_dir(&library).map_err(|e| e.to_string())? {
        let category = category.map_err(|e| e.to_string())?;
        let parent = category.file_name().to_string_lossy().into_owned();
        if ["RESTORE", "IGNORE", ".USER_PREFS"].contains(&parent.as_str()) || parent.starts_with('.') { continue; }
        plain_directory(&category.path(), false)?;
        for entry in fs::read_dir(category.path()).map_err(|e| e.to_string())? {
            let entry = entry.map_err(|e| e.to_string())?;
            if !entry.file_type().map_err(|e| e.to_string())?.is_dir() { continue; }
            plain_directory(&entry.path(), false)?;
            let count = pak_count(&entry.path())?;
            if count == 0 { continue; }
            let name = entry.file_name().to_string_lossy().into_owned();
            let path = format!("{parent}\\{name}");
            let relative = relative_mod(&path)?;
            let target_root = tgt.join(TARGET);
            let target_category = target_root.join(&parent);
            if fs::symlink_metadata(&target_root).is_ok() { plain_directory(&target_root, false)?; }
            if fs::symlink_metadata(&target_category).is_ok() { plain_directory(&target_category, false)?; }
            let enabled = owned_link(&tgt.join(TARGET).join(relative), &entry.path())?;
            result.push(PakMod { path, name, parent: parent.clone(), enabled, pak_count: count });
        }
    }
    result.sort_by(|a, b| a.path.cmp(&b.path));
    Ok(result)
}

#[tauri::command]
pub fn nte_validate_mod(source_dir: String, target_dir: String, mod_path: String) -> Result<usize, String> {
    let relative = relative_mod(&mod_path)?;
    let (src, _) = roots(&source_dir, &target_dir)?;
    let library = src.join(SOURCE);
    plain_directory(&library, false)?;
    plain_directory(&library.join(relative.parent().unwrap()), false)?;
    let original = library.join(relative);
    plain_directory(&original, false)?;
    let count = pak_count(&original)?;
    if count == 0 { return Err("Downloaded mod has no .pak file. Keep the pak, utoc and ucas files together.".into()); }
    Ok(count)
}

fn collect_paks(path: &Path, output: &mut Vec<PathBuf>) -> Result<(), String> {
    for entry in fs::read_dir(path).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let meta = fs::symlink_metadata(entry.path()).map_err(|e| e.to_string())?;
        if is_link(&meta) { return Err("Downloaded mod contains a redirected path".into()); }
        if meta.is_dir() { collect_paks(&entry.path(), output)?; }
        else if entry.path().extension().is_some_and(|x| x.eq_ignore_ascii_case("pak")) { output.push(entry.path()); }
    }
    Ok(())
}

#[tauri::command]
pub fn nte_split_variants(source_dir: String, target_dir: String, mod_path: String) -> Result<Vec<String>, String> {
    nte_validate_mod(source_dir.clone(), target_dir.clone(), mod_path.clone())?;
    let (src, tgt) = roots(&source_dir, &target_dir)?;
    let relative = relative_mod(&mod_path)?;
    let original = src.join(SOURCE).join(&relative);
    let mut paks = Vec::new();
    collect_paks(&original, &mut paks)?;
    if paks.len() == 1 { return Ok(vec![mod_path]); }
    if owned_link(&tgt.join(TARGET).join(&relative), &original)? {
        return Err("Disable this mod before splitting its pak alternatives".into());
    }
    let name = relative.file_name().unwrap().to_string_lossy();
    let category = relative.parent().unwrap();
    let mut planned = Vec::new();
    for (index, pak) in paks.iter().enumerate() {
        let stem = pak.file_stem().unwrap().to_string_lossy();
        let short_name: String = name.chars().take(80).collect();
        let short_stem: String = stem.chars().take(80).collect();
        let new_name = format!("{short_name} · {} · {short_stem}", index + 1);
        let new_relative = category.join(new_name);
        let destination = src.join(SOURCE).join(&new_relative);
        if fs::symlink_metadata(&destination).is_ok() { return Err("Pak variant destination already exists; refusing to overwrite".into()); }
        planned.push((pak.clone(), new_relative, destination));
    }
    // Preserve the downloaded documentation in the original, now non-loadable folder.
    let mut result = Vec::new();
    for (pak, new_relative, destination) in planned {
        fs::create_dir(&destination).map_err(|e| e.to_string())?;
        for file in fs::read_dir(pak.parent().unwrap()).map_err(|e| e.to_string())? {
            let file = file.map_err(|e| e.to_string())?;
            let file_path = file.path();
            if file_path.file_stem() == pak.file_stem()
                && file_path.extension().is_some_and(|x| ["pak", "utoc", "ucas"].iter().any(|e| x.eq_ignore_ascii_case(e))) {
                fs::rename(&file_path, destination.join(file.file_name())).map_err(|e| e.to_string())?;
            }
        }
        for entry in fs::read_dir(&original).map_err(|e| e.to_string())? {
            let entry = entry.map_err(|e| e.to_string())?;
            let name = entry.file_name().to_string_lossy().into_owned();
            if entry.file_type().map_err(|e| e.to_string())?.is_file() && name.starts_with("preview.") {
                fs::copy(entry.path(), destination.join(name)).map_err(|e| e.to_string())?;
            }
        }
        fs::write(destination.join("Original package.txt"), format!("Original package: {}\nPayload: {}\nDocumentation: {}\nSelect main files/components as required; do not enable alternative appearances together.", original.display(), pak.display(), original.display())).map_err(|e| e.to_string())?;
        result.push(new_relative.to_string_lossy().into_owned());
    }
    Ok(result)
}

#[tauri::command]
pub fn nte_toggle_mod(source_dir: String, target_dir: String, mod_path: String, enabled: bool) -> Result<(), String> {
    let relative = relative_mod(&mod_path)?;
    let (src, tgt) = roots(&source_dir, &target_dir)?;
    let library = src.join(SOURCE);
    plain_directory(&library, false)?;
    plain_directory(&library.join(relative.parent().unwrap()), false)?;
    let original = library.join(&relative);
    plain_directory(&original, false)?;
    let target = tgt.join(TARGET);
    if enabled || fs::symlink_metadata(&target).is_ok() { plain_directory(&target, enabled)?; }
    let category = target.join(relative.parent().unwrap());
    if enabled || fs::symlink_metadata(&category).is_ok() { plain_directory(&category, enabled)?; }
    let link = target.join(relative);
    let exists = owned_link(&link, &original)?;
    if enabled {
        if pak_count(&original)? == 0 { return Err("This mod does not contain a .pak file".into()); }
        if !exists {
            #[cfg(windows)]
            {
                // Junctions do not need Developer Mode and work across local NTFS volumes.
                junction::create(&original, &link).map_err(|e|
                    format!("Cannot create NTE link. Check write access to Paks/Mods: {e}"))?;
            }
            #[cfg(not(windows))]
            std::os::unix::fs::symlink(&original, &link).map_err(|e| e.to_string())?;
            if !owned_link(&link, &original)? { return Err("Failed to verify new mod link".into()); }
        }
    } else if exists {
        // Remove just the directory entry; never recursively remove a mod link.
        #[cfg(windows)]
        fs::remove_dir(&link).map_err(|e| e.to_string())?;
        #[cfg(not(windows))]
        fs::remove_file(&link).map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
pub fn nte_launch_loader(loader_path: String) -> Result<(), String> {
    let exe = fs::canonicalize(loader_path).map_err(|e| e.to_string())?;
    if !exe.is_file() || !exe.file_name().is_some_and(|n| n.eq_ignore_ascii_case("Mod注入器.exe")) {
        return Err("Choose the existing NTE Mod注入器.exe".into());
    }
    let parent = exe.parent().ok_or("Loader has no parent directory")?;
    if !parent.join("Mod Loader").join("Game start.exe").is_file() {
        return Err("Missing Mod Loader/Game start.exe alongside the injector".into());
    }
    std::process::Command::new(&exe).current_dir(parent).spawn().map_err(|e| e.to_string())?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;
    fn fixture() -> (TempDir, String, String, PathBuf) {
        let temp = tempfile::tempdir().unwrap();
        let source = temp.path().join("library");
        let target = temp.path().join("game/Content/Paks/Mods");
        let original = source.join(SOURCE).join("Mint/Test");
        fs::create_dir_all(&original).unwrap();
        fs::create_dir_all(&target).unwrap();
        fs::write(original.join("test_P.pak"), b"fixture").unwrap();
        (temp, source.to_string_lossy().into(), target.to_string_lossy().into(), original)
    }
    #[test]
    fn enable_disable_preserves_pak_and_plain_target() {
        let (_temp, src, tgt, original) = fixture();
        nte_toggle_mod(src.clone(), tgt.clone(), "Mint\\Test".into(), true).unwrap();
        assert!(nte_list_mods(src.clone(), tgt.clone()).unwrap()[0].enabled);
        nte_toggle_mod(src.clone(), tgt.clone(), "Mint/Test".into(), false).unwrap();
        nte_toggle_mod(src.clone(), tgt.clone(), "Mint/Test".into(), false).unwrap();
        assert_eq!(fs::read(original.join("test_P.pak")).unwrap(), b"fixture");
        let link = Path::new(&tgt).join(TARGET).join("Mint/Test");
        fs::create_dir(&link).unwrap();
        fs::write(link.join("foreign.pak"), b"keep").unwrap();
        assert!(nte_toggle_mod(src, tgt, "Mint/Test".into(), false).is_err());
        assert!(link.join("foreign.pak").exists());
    }
    #[test]
    fn refuses_traversal_and_in_game_library() {
        for path in ["../Test", "Mint/../Test", "C:/Test", "Mint", "Mint//Test", "Mint/."] {
            assert!(relative_mod(path).is_err(), "{path}");
        }
        let (_temp, _, tgt, _) = fixture();
        assert!(nte_prepare_storage(tgt.clone(), tgt).is_err());
    }
    #[test]
    fn refuses_non_pak_mods() {
        let (_temp, src, tgt, original) = fixture();
        fs::remove_file(original.join("test_P.pak")).unwrap();
        fs::write(original.join("readme.txt"), b"not a mod").unwrap();
        assert!(nte_list_mods(src.clone(), tgt.clone()).unwrap().is_empty());
        assert!(nte_toggle_mod(src, tgt, "Mint/Test".into(), true).is_err());
    }
    #[test]
    fn splits_alternatives_with_matching_companions() {
        let (_temp, src, tgt, original) = fixture();
        fs::write(original.join("test_P.utoc"), b"companion").unwrap();
        fs::create_dir(original.join("Alternative")).unwrap();
        fs::write(original.join("Alternative/other_P.pak"), b"alternative").unwrap();
        fs::write(original.join("readme.txt"), b"documentation").unwrap();
        let result = nte_split_variants(src.clone(), tgt.clone(), "Mint/Test".into()).unwrap();
        assert_eq!(result.len(), 2);
        assert!(original.join("readme.txt").exists());
        let mods = nte_list_mods(src.clone(), tgt).unwrap();
        assert_eq!(mods.len(), 2);
        assert!(mods.iter().all(|m| !m.enabled && m.pak_count == 1));
        assert!(result.iter().any(|r| Path::new(&src).join(SOURCE).join(r).join("test_P.utoc").exists()));
    }
}
