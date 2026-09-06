import { describe, expect, it } from 'vitest';
import {
	buildDrivers,
	buildEvents,
	buildPitLanePath,
	buildTrackPath,
	filterEvents,
	pitLaneProgressAt,
	positionAtTrackProgress,
	sampleAt,
	smoothPositionHolds,
	timingAt
} from './model';
import type { DriverMeta, LapRow, PositionRow } from './types';

const metadata: DriverMeta[] = [
	{
		driver_code: 'NOR',
		driver_name: 'Lando Norris',
		team: 'McLaren',
		team_color: '#ff8700',
		grid_position: 3,
		finish_position: 1,
		status: 'Finished',
		is_classified: true
	}
];
const laps: LapRow[] = [
	{
		driver_code: 'NOR',
		lap_number: 1,
		lap_start_t_s: 0,
		lap_time_sec: 80,
		stint: 1,
		compound: 'MEDIUM',
		tyre_life: 3
	}
];
const positions: PositionRow[] = [
	{
		driver_code: 'NOR',
		t_s: 0,
		x: 0,
		y: 0,
		running_order: 3,
		gap_to_leader_s: 2,
		gap_to_ahead_s: 1
	},
	{
		driver_code: 'NOR',
		t_s: 1,
		x: 10,
		y: 5,
		running_order: 2,
		gap_to_leader_s: 1,
		gap_to_ahead_s: 0.5
	}
];

describe('replay model', () => {
	it('interpolates positions and builds live timing context', () => {
		const drivers = buildDrivers(positions, metadata, laps);
		expect(sampleAt(drivers[0], 0.5)?.x).toBeCloseTo(5);
		expect(timingAt(drivers, 1)[0]).toMatchObject({
			code: 'NOR',
			order: 2,
			compound: 'MEDIUM',
			positionChange: 1
		});
	});

	it('smooths short sample-and-hold coordinate runs', () => {
		const samples = buildDrivers(
			[0, 1, 2, 3, 4, 5, 6].map((t, index) => ({
				...positions[0],
				t_s: t,
				x: index < 3 ? 10 : index < 6 ? 40 : 70,
				y: 5
			})),
			metadata,
			laps
		)[0].samples;

		expect(samples[2].x).toBeCloseTo(20);
		expect(samples[3].x).toBeCloseTo(30);
		expect(samples[4].x).toBeCloseTo(40);
	});

	it('keeps interpolation inside a sharp-corner segment', () => {
		const driver = buildDrivers(
			[
				{ ...positions[0], t_s: 0, x: -100, y: 100 },
				{ ...positions[0], t_s: 1, x: 0, y: 0 },
				{ ...positions[0], t_s: 2, x: 10, y: 0 },
				{ ...positions[0], t_s: 3, x: 110, y: 100 }
			],
			metadata,
			laps
		)[0];

		expect(sampleAt(driver, 1.5)).toMatchObject({ x: 5, y: 0 });
	});

	it('does not bridge a missing replay interval', () => {
		const driver = buildDrivers(
			[
				{ ...positions[0], t_s: 0, x: 10, y: 10 },
				{ ...positions[0], t_s: 1, x: 20, y: 10 },
				{ ...positions[0], t_s: 4, x: 40, y: 20 }
			],
			metadata,
			laps
		)[0];

		expect(sampleAt(driver, 2)).toBeNull();
		expect(sampleAt(driver, 4)?.x).toBe(40);
	});

	it('interpolates lap progress continuously between animation frames', () => {
		const driver = buildDrivers(positions, metadata, laps)[0];

		expect(sampleAt(driver, 0.5)?.lapProgress).toBeCloseTo(0.00625);
	});

	it('uses a stable complete lap as the canonical circuit', () => {
		const base = buildDrivers(positions, metadata, laps)[0];
		const cleanLap = Array.from({ length: 21 }, (_, index) => {
			const angle = (index / 20) * Math.PI * 2;
			return {
				...base.samples[0],
				t: index,
				x: Math.cos(angle) * 100,
				y: Math.sin(angle) * 100,
				lap: 1,
				lapProgress: index / 20
			};
		});
		const corruptLap = cleanLap.map((sample, index) => ({
			...sample,
			t: sample.t + 30,
			x: index % 2 ? 1000 : -1000,
			lap: 2
		}));
		const path = buildTrackPath([{ ...base, samples: [...cleanLap, ...corruptLap] }]);

		expect(path).not.toBeNull();
		expect(Math.max(...path!.points.map((point) => Math.abs(point.x)))).toBeLessThan(101);
		expect(path!.points.at(-1)).toEqual(path!.points[0]);
	});

	it('places cars on the canonical path by forward lap progress', () => {
		const path = {
			points: [
				{ x: 0, y: 0 },
				{ x: 10, y: 0 },
				{ x: 10, y: 10 },
				{ x: 0, y: 10 },
				{ x: 0, y: 0 }
			],
			cumulative: [0, 10, 20, 30, 40],
			length: 40
		};

		expect(positionAtTrackProgress(path, 0.125)).toEqual({ x: 5, y: 0 });
		expect(positionAtTrackProgress(path, 0.375)).toEqual({ x: 10, y: 5 });
		expect(positionAtTrackProgress(path, 0.625)).toEqual({ x: 5, y: 10 });
	});

	it('leaves long stationary periods intact', () => {
		const samples = [
			{ t: 0, x: 0, y: 1 },
			{ t: 1, x: 0, y: 1 },
			{ t: 20, x: 0, y: 1 },
			{ t: 21, x: 50, y: 1 }
		].map((sample) => ({
			...sample,
			order: 1,
			gap: 0,
			ahead: 0,
			lap: 1,
			lapProgress: 0,
			stint: 1,
			compound: 'MEDIUM',
			tyreLife: 1
		}));

		smoothPositionHolds(samples);

		expect(samples[2].x).toBe(0);
	});

	it('limits a driver selection to their radio and overtakes', () => {
		const events = buildEvents(
			[
				{
					t_s: 1,
					category: 'Flag',
					flag: 'GREEN',
					scope: 'Track',
					message: 'Green flag',
					driver_code: null
				}
			],
			[
				{
					t_s: 2,
					for_position: 2,
					passer_code: 'NOR',
					passed_code: 'VER',
					gap_at_pass_s: 0.1,
					confidence: 0.95,
					evidence: null,
					reason: null
				}
			],
			[
				{
					t_s: 3,
					driver_code: 'NOR',
					recording_url: 'https://example.com/radio.mp3',
					transcript: null
				}
			]
		);
		expect(filterEvents(events, 'NOR').map((event) => event.type)).toEqual(['overtake', 'radio']);
		expect(filterEvents(events, 'VER').map((event) => event.type)).toEqual(['overtake']);
		expect(filterEvents(events, '', 'control')).toHaveLength(1);
	});

	it('adds every driver stint transition to the event timeline as a pit stop', () => {
		const pitLaps: LapRow[] = [
			{ ...laps[0], driver_code: 'NOR', lap_number: 1, lap_start_t_s: 0, stint: 1 },
			{
				...laps[0],
				driver_code: 'NOR',
				lap_number: 2,
				lap_start_t_s: 80,
				stint: 2,
				compound: 'HARD'
			},
			{ ...laps[0], driver_code: 'VER', lap_number: 1, lap_start_t_s: 0, stint: 1 },
			{
				...laps[0],
				driver_code: 'VER',
				lap_number: 2,
				lap_start_t_s: 81,
				stint: 2,
				compound: 'MEDIUM'
			}
		];

		const events = buildEvents([], [], [], pitLaps);

		expect(events.map((event) => event.label)).toEqual(['NOR pit stop', 'VER pit stop']);
		expect(events[0]).toMatchObject({
			time: 80,
			type: 'pit',
			meta: 'Lap 1 · Stop 1 · Onto hard tyres',
			participants: ['NOR']
		});
		expect(filterEvents(events, 'VER', 'pit').map((event) => event.label)).toEqual([
			'VER pit stop'
		]);
	});

	it('creates a timed pit window around every stint transition', () => {
		const pitLaps: LapRow[] = [
			{ ...laps[0], lap_number: 1, lap_start_t_s: 0, stint: 1 },
			{ ...laps[0], lap_number: 2, lap_start_t_s: 20, stint: 2 }
		];
		const pitPositions: PositionRow[] = Array.from({ length: 61 }, (_, t) => ({
			...positions[0],
			t_s: t,
			x: t >= 15 && t <= 40 ? 500 : t * 10,
			y: 0
		}));
		const driver = buildDrivers(pitPositions, metadata, pitLaps)[0];

		expect(driver.pitWindows).toEqual([{ start: 8, stop: 20, end: 32 }]);
		expect(pitLaneProgressAt(driver, 8)).toBe(0);
		expect(pitLaneProgressAt(driver, 20)).toBe(0.5);
		expect(pitLaneProgressAt(driver, 21)).toBe(0.5);
		expect(pitLaneProgressAt(driver, 32)).toBe(1);
		expect(pitLaneProgressAt(driver, 33)).toBeNull();
	});

	it('builds a compact pit lane around the start and finish line', () => {
		const track = {
			points: [
				{ x: 0, y: 0 },
				{ x: 10, y: 0 },
				{ x: 10, y: 10 },
				{ x: 0, y: 10 },
				{ x: 0, y: 0 }
			],
			cumulative: [0, 10, 20, 30, 40],
			length: 40
		};
		const path = buildPitLanePath(track);

		expect(path?.points).toHaveLength(33);
		expect(path?.points[0]).toEqual(positionAtTrackProgress(track, 0.91));
		expect(path?.points.at(-1)?.x).toBeCloseTo(positionAtTrackProgress(track, 0.09).x);
		expect(path?.points.at(-1)?.y).toBeCloseTo(positionAtTrackProgress(track, 0.09).y);
		expect(path?.length).toBeLessThan(track.length / 2);
		expect(path?.box).not.toEqual(positionAtTrackProgress(track, 0));
	});
});
