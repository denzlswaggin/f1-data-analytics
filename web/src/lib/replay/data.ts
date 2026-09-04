import { base } from '$app/paths';
import { tableFromIPC } from 'apache-arrow';
import type { LoadedRace, PositionRow, RaceBundle, RaceSummary, ReplayManifest } from './types';

async function checkedFetch(url: string, signal?: AbortSignal) {
	const response = await fetch(url, { signal });
	if (!response.ok) throw new Error(`Could not load ${url} (${response.status})`);
	return response;
}

export async function loadManifest(signal?: AbortSignal): Promise<ReplayManifest> {
	const response = await checkedFetch(`${base}/data/manifest.json`, signal);
	const manifest = (await response.json()) as ReplayManifest;
	if (manifest.schema_version !== 1 || !manifest.races?.length) {
		throw new Error('No compatible race replay data is available.');
	}
	return manifest;
}

export async function loadRace(summary: RaceSummary, signal?: AbortSignal): Promise<LoadedRace> {
	const [bundleResponse, positionsResponse] = await Promise.all([
		checkedFetch(`${base}/data/${summary.bundle_url}`, signal),
		checkedFetch(`${base}/data/${summary.positions_url}`, signal)
	]);
	const [bundle, bytes] = await Promise.all([
		bundleResponse.json() as Promise<RaceBundle>,
		positionsResponse.arrayBuffer()
	]);
	const table = tableFromIPC(new Uint8Array(bytes));
	const code = table.getChild('driver_code');
	const time = table.getChild('t_s');
	const x = table.getChild('x');
	const y = table.getChild('y');
	const order = table.getChild('running_order');
	const leaderGap = table.getChild('gap_to_leader_s');
	const aheadGap = table.getChild('gap_to_ahead_s');
	if (!code || !time || !x || !y || !order || !leaderGap || !aheadGap) {
		throw new Error('The replay position bundle has an incompatible schema.');
	}
	const positions: PositionRow[] = new Array(table.numRows);
	for (let index = 0; index < table.numRows; index += 1) {
		positions[index] = {
			driver_code: String(code.get(index)),
			t_s: Number(time.get(index)),
			x: Number(x.get(index)),
			y: Number(y.get(index)),
			running_order: order.get(index) == null ? null : Number(order.get(index)),
			gap_to_leader_s: leaderGap.get(index) == null ? null : Number(leaderGap.get(index)),
			gap_to_ahead_s: aheadGap.get(index) == null ? null : Number(aheadGap.get(index))
		};
	}
	return { summary, bundle, positions };
}
