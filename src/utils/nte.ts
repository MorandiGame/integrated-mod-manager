import { invoke } from "@tauri-apps/api/core";
import { managedSRC } from "./consts";
import { getModData, join } from "./hotreload";
import { DATA, MOD_LIST, SETTINGS, SOURCE, TARGET, store } from "./vars";
import { toFs } from "./pathsep";
import type { Mod } from "./types";

export const NTE_SOURCE = "F:/ntemod";
export const NTE_TARGET = "C:/Program Files/Neverness To Everness/Client/WindowsNoEditor/HT/Content/Paks/Mods";
export const NTE_LOADER = "F:/ntemod/Loader/Mod注入器.exe";
export const isNte = () => store.get(SETTINGS).global.game === "NTE";

export async function prepareNteStorage() {
	await invoke("nte_prepare_storage", { sourceDir: toFs(store.get(SOURCE)), targetDir: toFs(store.get(TARGET)) });
}

export async function listNteMods(update = false): Promise<Mod[]> {
	const entries = await invoke<Array<{path: string; name: string; parent: string; enabled: boolean; pakCount: number}>>("nte_list_mods", {
		sourceDir: toFs(store.get(SOURCE)), targetDir: toFs(store.get(TARGET)),
	});
	const data = store.get(DATA);
	const mods = entries.map((entry): Mod => ({
		...getModData(data, entry.path), ...entry,
		isDir: true, depth: 1, children: [], keys: [], files: {}, hashes: [], namespaces: new Set(), maxed: false,
	}));
	if (update) store.set(MOD_LIST, mods);
	return mods;
}

export async function toggleNteMod(modPath: string, enabled: boolean) {
	await invoke("nte_toggle_mod", {
		sourceDir: toFs(store.get(SOURCE)), targetDir: toFs(store.get(TARGET)), modPath, enabled,
	});
	return true;
}

export async function launchNteLoader() {
	await invoke("nte_launch_loader", { loaderPath: toFs(store.get(SETTINGS).game.nteLoader || NTE_LOADER) });
}

export const nteLibrary = () => join(store.get(SOURCE), managedSRC);
