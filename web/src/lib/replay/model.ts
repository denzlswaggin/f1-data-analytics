import type {
	DriverMeta,
	LapRow,
	OvertakeRow,
	PositionRow,
	RaceControlRow,
	RadioRow,
	ReplayDriver,
	ReplayEvent,
	ReplaySample,
	TimingRow
} from './types';

const numberOrNull = (value: unknown): number | null => {
	if (value == null || value === '') return null;
	const converted = Number(value);
	return Number.isFinite(converted) ? converted : null;
};

export function buildDrivers(
	positions: PositionRow[],
	metadata: DriverMeta[],
	laps: LapRow[]
): ReplayDriver[] {
	const meta = new Map(metadata.map((driver) => [driver.driver_code, driver]));
	const lapGroups = new Map<string, LapRow[]>();
	for (const lap of laps) {
		const group = lapGroups.get(lap.driver_code) ?? [];
		group.push(lap);
		lapGroups.set(lap.driver_code, group);
	}
	for (const group of lapGroups.values()) group.sort((a, b) => a.lap_start_t_s - b.lap_start_t_s);

	const groups = new Map<string, ReplaySample[]>();
	for (const row of positions) {
		const driverLaps = lapGroups.get(row.driver_code) ?? [];
		let lo = 0;
		let hi = driverLaps.length;
		while (lo < hi) {
			const mid = (lo + hi) >> 1;
			if (driverLaps[mid].lap_start_t_s <= row.t_s) lo = mid + 1;
			else hi = mid;
		}
		const lap = driverLaps[lo - 1];
		const samples = groups.get(row.driver_code) ?? [];
		samples.push({
			t: row.t_s,
			x: row.x,
			y: row.y,
			order: numberOrNull(row.running_order),
			gap: numberOrNull(row.gap_to_leader_s),
			ahead: numberOrNull(row.gap_to_ahead_s),
			lap: lap?.lap_number ?? null,
			lapProgress:
				lap?.lap_time_sec && lap.lap_time_sec > 0
					? Math.max(0, Math.min(1, (row.t_s - lap.lap_start_t_s) / lap.lap_time_sec))
					: null,
			stint: lap?.stint ?? null,
			compound: lap?.compound ?? null,
			tyreLife: lap?.tyre_life ?? null
		});
		groups.set(row.driver_code, samples);
	}

	return [...groups.entries()].map(([code, samples]) => {
		samples.sort((a, b) => a.t - b.t);
		const info = meta.get(code);
		return {
			code,
			name: info?.driver_name || code,
			team: info?.team || '',
			color: info?.team_color || '#9aa0a6',
			startOrder: numberOrNull(info?.grid_position),
			finishPosition: numberOrNull(info?.finish_position),
			isClassified: info?.is_classified ?? null,
			resultStatus: info?.status ?? null,
			tmin: samples[0]?.t ?? 0,
			tmax: samples.at(-1)?.t ?? 0,
			samples
		};
	});
}

function catmull(q0: number, q1: number, q2: number, q3: number, fraction: number) {
	const squared = fraction * fraction;
	const cubed = squared * fraction;
	return (
		0.5 *
		(2 * q1 +
			(-q0 + q2) * fraction +
			(2 * q0 - 5 * q1 + 4 * q2 - q3) * squared +
			(-q0 + 3 * q1 - 3 * q2 + q3) * cubed)
	);
}

export function sampleAt(driver: ReplayDriver, time: number): ReplaySample | null {
	if (time < driver.tmin || time > driver.tmax || !driver.samples.length) return null;
	const samples = driver.samples;
	let lo = 0;
	let hi = samples.length - 1;
	while (lo < hi) {
		const mid = (lo + hi) >> 1;
		if (samples[mid].t < time) lo = mid + 1;
		else hi = mid;
	}
	if (lo <= 0) return samples[0];
	const previous = samples[lo - 1];
	const next = samples[lo];
	if (time === next.t) return next;
	const fraction = (time - previous.t) / (next.t - previous.t || 1);
	const before = samples[lo - 2] || previous;
	const after = samples[lo + 1] || next;
	const smooth =
		next.t - previous.t <= 1.5 && previous.t - before.t <= 1.5 && after.t - next.t <= 1.5;
	return {
		...previous,
		x: smooth
			? catmull(before.x, previous.x, next.x, after.x, fraction)
			: previous.x + (next.x - previous.x) * fraction,
		y: smooth
			? catmull(before.y, previous.y, next.y, after.y, fraction)
			: previous.y + (next.y - previous.y) * fraction
	};
}

export function timingAt(drivers: ReplayDriver[], time: number): TimingRow[] {
	const rows: TimingRow[] = [];
	for (const driver of drivers) {
		let sample = sampleAt(driver, time);
		let status: TimingRow['status'] = 'racing';
		if (!sample && time > driver.tmax && driver.samples.length) {
			sample = driver.samples.at(-1) ?? null;
			status =
				driver.isClassified === true
					? 'finished'
					: driver.isClassified === false
						? 'retired'
						: 'out';
		}
		if (!sample || sample.order == null) continue;
		rows.push({
			code: driver.code,
			name: driver.name,
			team: driver.team,
			color: driver.color,
			order: sample.order,
			gap: sample.gap,
			ahead: sample.ahead,
			lap: sample.lap,
			lapProgress: sample.lapProgress,
			stint: sample.stint,
			compound: sample.compound,
			tyreLife: sample.tyreLife,
			stops: sample.stint == null ? null : Math.max(0, sample.stint - 1),
			positionChange: driver.startOrder == null ? null : driver.startOrder - Number(sample.order),
			status
		});
	}
	return rows.sort((a, b) => Number(a.order) - Number(b.order));
}

function messageSubtype(row: RaceControlRow) {
	const flag = String(row.flag || '').toUpperCase();
	const category = String(row.category || '').toUpperCase();
	const message = String(row.message || '').toUpperCase();
	if (flag === 'RED' || message.includes('RED FLAG')) return 'red';
	if (flag === 'GREEN') return 'green';
	if (category === 'SAFETYCAR' || message.includes('SAFETY CAR') || message.includes('VSC'))
		return 'safety';
	if (flag.includes('YELLOW')) return 'yellow';
	if (message.includes('DRS ENABLED')) return 'drs';
	return 'control';
}

export function buildEvents(
	messages: RaceControlRow[],
	overtakes: OvertakeRow[],
	radio: RadioRow[]
): ReplayEvent[] {
	const events: ReplayEvent[] = [];
	messages.forEach((row, index) => {
		if (!Number.isFinite(row.t_s)) return;
		events.push({
			id: `control|${row.t_s}|${index}`,
			time: row.t_s,
			type: 'control',
			subtype: messageSubtype(row),
			label: row.message || row.category || row.flag || 'Race control update',
			meta: [row.flag, row.category].filter(Boolean).join(' · '),
			participants: row.driver_code ? [row.driver_code] : [],
			raw: row
		});
	});
	overtakes.forEach((row, index) => {
		if (!Number.isFinite(row.t_s)) return;
		events.push({
			id: `overtake|${row.t_s}|${index}`,
			time: row.t_s,
			type: 'overtake',
			subtype: 'overtake',
			label: `${row.passer_code} passes ${row.passed_code}`,
			meta: `${row.for_position == null ? 'Detected pass' : `For P${row.for_position}`}${row.confidence == null ? '' : ` · ${Math.round(row.confidence * 100)}% confidence`}`,
			participants: [row.passer_code, row.passed_code],
			raw: row
		});
	});
	radio.forEach((row, index) => {
		if (!Number.isFinite(row.t_s) || !row.recording_url) return;
		events.push({
			id: `radio|${row.t_s}|${index}`,
			time: row.t_s,
			type: 'radio',
			subtype: 'radio',
			label: row.transcript || `${row.driver_code} team radio`,
			meta: `${row.driver_code} team radio`,
			participants: [row.driver_code],
			raw: row
		});
	});
	return events.sort((a, b) => a.time - b.time || a.id.localeCompare(b.id));
}

export function filterEvents(events: ReplayEvent[], selectedCode: string, filter = 'all') {
	return events.filter((event) => {
		if (selectedCode && (event.type === 'control' || !event.participants.includes(selectedCode)))
			return false;
		return filter === 'all' || event.type === filter;
	});
}
