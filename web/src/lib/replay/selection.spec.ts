import { expect, it } from 'vitest';
import { latestRaceForSeason } from './selection';

it('chooses the last available round in the requested season regardless of manifest order', () => {
	const races = [
		{ season: 2025, round: 23 },
		{ season: 2026, round: 3 },
		{ season: 2026, round: 12 },
		{ season: 2025, round: 24 },
		{ season: 2026, round: 1 }
	];
	expect(latestRaceForSeason(races, 2026)).toEqual({ season: 2026, round: 12 });
	expect(latestRaceForSeason(races, 2025)).toEqual({ season: 2025, round: 24 });
	expect(latestRaceForSeason(races, 2024)).toBeUndefined();
	expect(latestRaceForSeason([], 2026)).toBeUndefined();
});
