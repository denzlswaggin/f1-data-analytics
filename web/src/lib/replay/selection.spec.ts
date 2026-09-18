import { expect, it } from 'vitest';
import { initialRace, latestRaceForSeason } from './selection';

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

it('preserves explicit race links instead of silently showing the default', () => {
	const races = [
		{ key: '2025-1', season: 2025, round: 1 },
		{ key: '2026-14', season: 2026, round: 14 }
	];
	expect(initialRace(races, '2026-14', new URLSearchParams('season=2025&race=1')).key).toBe(
		'2025-1'
	);
	expect(initialRace(races, '2026-14', new URLSearchParams()).key).toBe('2026-14');
	expect(initialRace(races, '2026-14', new URLSearchParams('season=2025')).key).toBe('2025-1');
	expect(() => initialRace(races, '2026-14', new URLSearchParams('season=2022&race=1'))).toThrow(
		'unavailable'
	);
	expect(() => initialRace([], '', new URLSearchParams())).toThrow('No replay races');
});
