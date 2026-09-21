import { describe, it, expect } from 'vitest';
import { buildPitVisits, buildEvents, pitLaneProgressAt } from './model';
import type { LapRow, ReplayDriver } from './types';
const lap = (n: number, extra: Partial<LapRow> = {}): LapRow => ({
	driver_code: 'NOR',
	lap_number: n,
	lap_start_t_s: (n - 1) * 80,
	lap_time_sec: 80,
	stint: 1,
	compound: 'MEDIUM',
	tyre_life: n,
	...extra
});
describe('pit visits', () => {
	it('keeps a zero timestamp and ignores nonfinite or pre-race boundaries', () => {
		const visits = buildPitVisits([
			lap(1, { pit_entry_t_s: 0, pit_exit_t_s: 20 }),
			lap(2, { pit_entry_t_s: NaN, pit_exit_t_s: Infinity }),
			lap(3, { pit_entry_t_s: -2 })
		]);
		expect(visits).toHaveLength(1);
		expect(visits[0]).toMatchObject({ entry: 0, exit: 20, source: 'recorded' });
	});
	it('uses recorded boundaries, deduplicates transitions and identifies tyres', () => {
		const rows = [
			lap(1, { pit_entry_t_s: 75 }),
			lap(2, { pit_exit_t_s: 102, stint: 2, compound: 'HARD' })
		];
		const visits = buildPitVisits(rows);
		expect(visits).toHaveLength(1);
		expect(visits[0]).toMatchObject({
			entry: 75,
			exit: 102,
			source: 'recorded',
			tyreChange: true,
			toCompound: 'HARD',
			window: { start: 75, end: 102, stop: 88.5 }
		});
		expect(buildEvents([], [], [], rows)[0].pitVisit).toEqual(visits[0]);
	});
	it('keeps recorded visits without a stint change', () => {
		expect(
			buildPitVisits([lap(1, { pit_entry_t_s: 75 }), lap(2, { pit_exit_t_s: 102 })])[0]
		).toMatchObject({ source: 'recorded', tyreChange: false, toCompound: null });
	});
	it('preserves incomplete and reversed boundaries without measured duration', () => {
		const visits = buildPitVisits([lap(1, { pit_exit_t_s: 10, pit_entry_t_s: 20 })]);
		expect(visits).toHaveLength(2);
		expect(visits.every((v) => v.window === null && v.source === 'incomplete')).toBe(true);
	});
	it('does not pair across another entry and deduplicates repeated packets', () => {
		const visits = buildPitVisits([
			lap(1, { pit_entry_t_s: 10 }),
			lap(2, { pit_entry_t_s: 20, pit_exit_t_s: 30 }),
			lap(3, { pit_exit_t_s: 30 })
		]);
		expect(visits).toHaveLength(2);
		expect(visits[0].window).toBeNull();
		expect(visits[1].window).toMatchObject({ start: 20, end: 30 });
	});
	it('supports legacy bundles and partial measured boundaries with estimated playback', () => {
		expect(buildPitVisits([lap(1), lap(2, { stint: 2 })])[0].source).toBe('estimated');
		const v = buildPitVisits([lap(1, { pit_entry_t_s: 75 }), lap(2, { stint: 2 })])[0];
		expect(v.source).toBe('incomplete');
		expect(v.exit).toBeNull();
		expect(v.window?.start).toBe(75);
	});
	it('scrubs continuously without invented stationary time', () => {
		const driver = { pitWindows: [{ start: 10, stop: 20, end: 30 }] } as ReplayDriver;
		expect([10, 19, 20, 21, 30, 19].map((t) => pitLaneProgressAt(driver, t))).toEqual([
			0, 0.45, 0.5, 0.55, 1, 0.45
		]);
	});
});
