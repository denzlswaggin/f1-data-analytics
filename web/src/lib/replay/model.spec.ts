import { describe, expect, it } from 'vitest';
import {
	buildDrivers,
	buildEvents,
	buildPitLanePath,
	buildTrackPath,
	filterEvents,
	formatLapTime,
	radioEventsForPhase,
	pitLaneProgressAt,
	positionAtTrackProgress,
	projectedSampleAt,
	sampleAt,
	smoothPositionHolds,
	timingAt,
	weatherAtTime
} from './model';
import type { DriverMeta, LapRow, PositionRow, RadioRow, WeatherRow } from './types';
import { pitLaneProfileFor, supportedPitLaneCircuits } from './pit-lanes';

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
	it.each([
		[true, 'Engine', 'classified'],
		[true, 'Lapped', 'classified'],
		[false, 'Disqualified', 'not classified'],
		[null, null, 'out']
	] as const)('keeps classification separate from finishing: %s %s', (flag, result, label) => {
		const drivers = buildDrivers(
			positions,
			[{ ...metadata[0], is_classified: flag, status: result }],
			laps
		);
		expect(timingAt(drivers, 100)[0].status).toBe(label);
		expect(sampleAt(drivers[0], 100)).toBeNull();
	});

	it('formats lap durations as minutes and seconds', () => {
		expect(formatLapTime(79.842)).toBe('1:19.842');
		expect(formatLapTime(60)).toBe('1:00.000');
		expect(formatLapTime(null)).toBe('—');
	});

	it('uses the latest available weather sample at replay time', () => {
		const weather: WeatherRow[] = [
			{
				t_s: 0,
				air_temperature: 20,
				track_temperature: 30,
				humidity: 50,
				pressure: 1012,
				rainfall: false,
				wind_direction: 180,
				wind_speed: 2
			},
			{
				t_s: 60,
				air_temperature: 19,
				track_temperature: 27,
				humidity: 68,
				pressure: 1011,
				rainfall: true,
				wind_direction: 210,
				wind_speed: 4
			}
		];

		expect(weatherAtTime([], 10)).toBeNull();
		expect(weatherAtTime(weather, -10)).toBe(weather[0]);
		expect(weatherAtTime(weather, 59)).toBe(weather[0]);
		expect(weatherAtTime(weather, 60)).toBe(weather[1]);
		expect(weatherAtTime(weather, 500)).toBe(weather[1]);
	});

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
					transcript: null,
					phase: 'race'
				}
			]
		);
		expect(filterEvents(events, 'NOR').map((event) => event.type)).toEqual(['overtake', 'radio']);
		expect(filterEvents(events, 'VER').map((event) => event.type)).toEqual(['overtake']);
		expect(filterEvents(events, '', 'control')).toHaveLength(1);
		const pass = events.find((event) => event.type === 'overtake');
		expect(pass?.label).toContain('model-detected pass');
		expect(pass?.meta).toContain('event accuracy unverified');
		expect(pass?.meta).not.toContain('%');
		expect(pass?.raw).toMatchObject({ confidence: 0.95 });
	});

	it('keeps live timeline events inside the replay duration', () => {
		const messages = [
			{
				t_s: 99,
				category: 'Flag',
				flag: 'CHEQUERED',
				scope: 'Track',
				message: 'Chequered flag',
				driver_code: null
			},
			{
				t_s: 108,
				category: 'Other',
				flag: null,
				scope: 'Track',
				message: 'Post-race investigation',
				driver_code: null
			}
		];

		expect(buildEvents(messages, [], [], [], '', 100).map((event) => event.time)).toEqual([99]);
	});

	it('keeps pre-race and post-race radio out of the live race timeline', () => {
		const radio: RadioRow[] = [
			{
				t_s: -40,
				driver_code: 'NOR',
				recording_url: 'https://example.com/pre.mp3',
				transcript: 'Radio check',
				phase: 'pre-race'
			},
			{
				t_s: 12,
				driver_code: 'NOR',
				recording_url: 'https://example.com/race.mp3',
				transcript: 'Box this lap',
				phase: 'race'
			},
			{
				t_s: 105,
				driver_code: 'VER',
				recording_url: 'https://example.com/post.mp3',
				transcript: 'Well done',
				phase: 'post-race'
			}
		];

		expect(buildEvents([], [], radio).map((event) => event.label)).toEqual(['Box this lap']);
		expect(radioEventsForPhase(radio, 'pre-race').map((event) => event.label)).toEqual([
			'Radio check'
		]);
		expect(radioEventsForPhase(radio, 'post-race', 'NOR')).toEqual([]);
		expect(radioEventsForPhase(radio, 'post-race', 'VER')[0].time).toBe(105);
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

		const events = buildEvents([], [], [], pitLaps, 'Hungaroring');

		expect(events.map((event) => event.label)).toEqual(['NOR pit stop', 'VER pit stop']);
		expect(events[0]).toMatchObject({
			type: 'pit',
			meta: 'Lap 1 · Stop 1 · Onto hard tyres',
			participants: ['NOR']
		});
		expect(events[0].time).toBeCloseTo(89.23);
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
		const driver = buildDrivers(pitPositions, metadata, pitLaps, 'Hungaroring')[0];

		expect(driver.pitWindows[0].start).toBeCloseTo(18.32);
		expect(driver.pitWindows[0].stop).toBeCloseTo(29.23);
		expect(driver.pitWindows[0].end).toBeCloseTo(40.14);
		expect(pitLaneProgressAt(driver, 18.32)).toBeCloseTo(0);
		expect(pitLaneProgressAt(driver, 29.23)).toBe(0.5);
		expect(pitLaneProgressAt(driver, 30)).toBe(0.5);
		expect(pitLaneProgressAt(driver, 40.14)).toBe(1);
		expect(pitLaneProgressAt(driver, 41)).toBeNull();
	});

	it('keeps a car renderable through a position-feed gap while it is in pit lane', () => {
		const pitLaps: LapRow[] = [
			{ ...laps[0], lap_number: 1, lap_start_t_s: 0, stint: 1 },
			{ ...laps[0], lap_number: 2, lap_start_t_s: 20, stint: 2 }
		];
		const sparsePositions: PositionRow[] = [0, 18, 22, 40, 42].map((t) => ({
			...positions[0],
			t_s: t,
			x: t,
			y: 0
		}));
		const driver = buildDrivers(sparsePositions, metadata, pitLaps, 'Hungaroring')[0];

		expect(sampleAt(driver, 10)).toBeNull();
		expect(sampleAt(driver, driver.pitWindows[0].stop)).not.toBeNull();
	});

	it('has measured entry and exit profiles for every published circuit', () => {
		expect(supportedPitLaneCircuits).toHaveLength(24);
		expect(pitLaneProfileFor('Hungaroring')).toEqual({
			entryProgress: 0.96,
			exitProgress: 0.08,
			entryLeadSeconds: 1.68,
			exitLagSeconds: 20.14
		});
		expect(pitLaneProfileFor('Autódromo José Carlos Pace')).toEqual({
			entryProgress: 0.9778,
			exitProgress: 0.0721,
			entryLeadSeconds: 2.83,
			exitLagSeconds: 21.12
		});
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
		const path = buildPitLanePath(track, 'Hungaroring');

		expect(path?.points).toHaveLength(33);
		expect(path?.points[0]).toEqual(positionAtTrackProgress(track, 0.96));
		expect(path?.points.at(-1)?.x).toBeCloseTo(positionAtTrackProgress(track, 0.08).x);
		expect(path?.points.at(-1)?.y).toBeCloseTo(positionAtTrackProgress(track, 0.08).y);
		expect(path?.length).toBeLessThan(track.length / 2);
		expect(path?.box).not.toEqual(positionAtTrackProgress(track, 0));
	});

	it('blends into and out of the pit lane without teleporting', () => {
		const pitLaps: LapRow[] = [
			{ ...laps[0], lap_number: 1, lap_start_t_s: 0, stint: 1 },
			{ ...laps[0], lap_number: 2, lap_start_t_s: 20, stint: 2 }
		];
		const pitPositions: PositionRow[] = Array.from({ length: 61 }, (_, t) => ({
			...positions[0],
			t_s: t,
			x: t,
			y: 0
		}));
		const driver = buildDrivers(pitPositions, metadata, pitLaps, 'Hungaroring')[0];
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
		const pitLane = buildPitLanePath(track, 'Hungaroring')!;
		const window = driver.pitWindows[0];
		const distance = (left: { x: number; y: number }, right: { x: number; y: number }) =>
			Math.hypot(left.x - right.x, left.y - right.y);
		const beforeEntry = projectedSampleAt(driver, window.start - 0.001, track, pitLane)!;
		const entry = projectedSampleAt(driver, window.start, track, pitLane)!;
		const exit = projectedSampleAt(driver, window.end, track, pitLane)!;
		const afterExit = projectedSampleAt(driver, window.end + 0.001, track, pitLane)!;
		const stopped = projectedSampleAt(driver, window.stop, track, pitLane)!;

		expect(distance(beforeEntry, entry)).toBeLessThan(0.01);
		expect(distance(exit, afterExit)).toBeLessThan(0.01);
		expect(stopped.x).toBeCloseTo(pitLane.box.x);
		expect(stopped.y).toBeCloseTo(pitLane.box.y);
		const held = projectedSampleAt(driver, window.stop + 1, track, pitLane)!;
		expect(held.x).toBeCloseTo(pitLane.box.x);
		expect(held.y).toBeCloseTo(pitLane.box.y);
	});
});


it('keeps order and gap provenance attached to the held timing sample', () => {
    const rows = positions.map((row, index) => ({ ...row,
        running_order_source: index === 0 ? 'openf1_recorded' : 'lap_progress_estimate',
        gap_source: index === 0 ? 'lap_progress_estimate' : null
    }));
    const drivers = buildDrivers(rows, metadata, laps);
    expect(timingAt(drivers, 0.5)[0].orderSource).toBe('openf1_recorded');
    expect(timingAt(drivers, 0.5)[0].gapSource).toBe('lap_progress_estimate');
    expect(timingAt(drivers, 1)[0].orderSource).toBe('lap_progress_estimate');
    expect(timingAt(drivers, 1)[0].gapSource).toBeNull();
});
