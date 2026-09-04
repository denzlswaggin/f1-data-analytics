import { describe, expect, it } from 'vitest';
import { buildDrivers, buildEvents, filterEvents, sampleAt, timingAt } from './model';
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
});
