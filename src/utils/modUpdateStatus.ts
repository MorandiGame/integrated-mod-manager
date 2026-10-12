export type ObservedFileVersions = Record<string, number>;

export function latestModFileDate(files: unknown): number {
	if (!Array.isArray(files)) return 0;
	return files.reduce((latest: number, file) => {
		const timestamp = Number(file?._tsDateModified || file?._tsDateAdded || 0) * 1000;
		return Number.isFinite(timestamp) && timestamp > 1 ? Math.max(latest, timestamp) : latest;
	}, 0);
}

/** Unknown imported versions are observations, not evidence of an installed old file. */
export function modUpdateStatus(
	item: { updated: number; viewed: number; observationKey: string },
	latest: number,
	observations: ObservedFileVersions,
): 0 | 1 | 2 {
	if (!Number.isFinite(latest) || latest <= 1) return 0;
	let baseline = Number.isFinite(item.updated) && item.updated > 1 ? item.updated : 0;
	if (!baseline) {
		baseline = observations[item.observationKey] || 0;
		if (!Number.isFinite(baseline) || baseline <= 1) {
			observations[item.observationKey] = latest;
			return 0;
		}
	}
	return latest > baseline ? (item.viewed >= latest ? 1 : 2) : 0;
}
