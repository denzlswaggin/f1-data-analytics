import type {
	DriverMeta,
	LapRow,
	OvertakeRow,
	PitLanePath,
	PositionRow,
	RaceControlRow,
	RadioRow,
	ReplayDriver,
	ReplayEvent,
	ReplaySample,
	TrackPath,
	TrackPoint,
	TimingRow
} from './types';

const numberOrNull = (value: unknown): number | null => {
	if (value == null || value === '') return null;
	const converted = Number(value);
	return Number.isFinite(converted) ? converted : null;
};

const POSITION_EPSILON = 0.5;
const MAX_HOLD_INTERPOLATION_S = 10;
const MAX_REPLAY_SAMPLE_GAP_S = 1.5;
const PIT_WINDOW_LEAD_S = 12;
const PIT_WINDOW_LAG_S = 12;
const PIT_STOP_HOLD_S = 3;

/**
 * Redistribute short sample-and-hold coordinate runs without changing timing data.
 *
 * Published bundles may predate the equivalent pipeline clean-up, so this is also
 * a backwards-compatible guard for already deployed Arrow files. Long stationary
 * runs are left alone because they can be a red flag or a genuinely stopped car.
 */
export function smoothPositionHolds(samples: ReplaySample[]) {
	if (samples.length < 3) return samples;
	const starts = [0];
	for (let index = 1; index < samples.length; index += 1) {
		if (
			Math.hypot(samples[index].x - samples[index - 1].x, samples[index].y - samples[index - 1].y) >
			POSITION_EPSILON
		) {
			starts.push(index);
		}
	}
	if (starts.length < 2) return samples;

	const anchors = starts.map((start, index) => {
		const end = (starts[index + 1] ?? samples.length) - 1;
		return {
			t: index === starts.length - 1 ? samples[start].t : (samples[start].t + samples[end].t) / 2,
			x: samples[start].x,
			y: samples[start].y
		};
	});
	let right = 1;
	for (const sample of samples) {
		while (right < anchors.length && anchors[right].t < sample.t) right += 1;
		if (right >= anchors.length) break;
		const previous = anchors[right - 1];
		const next = anchors[right];
		const gap = next.t - previous.t;
		if (sample.t < previous.t || gap <= 0 || gap > MAX_HOLD_INTERPOLATION_S) continue;
		const fraction = Math.max(0, Math.min(1, (sample.t - previous.t) / gap));
		sample.x = previous.x + (next.x - previous.x) * fraction;
		sample.y = previous.y + (next.y - previous.y) * fraction;
	}
	return samples;
}

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
		smoothPositionHolds(samples);
		const pitWindows: ReplayDriver['pitWindows'] = [];
		const driverLaps = lapGroups.get(code) ?? [];
		for (let index = 1; index < driverLaps.length; index += 1) {
			const previous = driverLaps[index - 1];
			const lap = driverLaps[index];
			if (
				previous.stint != null &&
				lap.stint != null &&
				lap.stint > previous.stint &&
				Number.isFinite(lap.lap_start_t_s)
			) {
				pitWindows.push({
					start: Math.max(samples[0].t, lap.lap_start_t_s - PIT_WINDOW_LEAD_S),
					stop: lap.lap_start_t_s,
					end: Math.min(samples.at(-1)!.t, lap.lap_start_t_s + PIT_WINDOW_LAG_S)
				});
			}
		}
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
			samples,
			pitWindows
		};
	});
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
	if (next.t - previous.t > MAX_REPLAY_SAMPLE_GAP_S) return null;
	const fraction = (time - previous.t) / (next.t - previous.t || 1);
	let lap = previous.lap;
	let lapProgress = previous.lapProgress;
	if (previous.lapProgress != null && next.lapProgress != null) {
		if (previous.lap === next.lap) {
			lapProgress = previous.lapProgress + (next.lapProgress - previous.lapProgress) * fraction;
		} else if (previous.lap != null && next.lap === previous.lap + 1) {
			const unwrapped =
				previous.lapProgress + (next.lapProgress + 1 - previous.lapProgress) * fraction;
			lap = unwrapped >= 1 ? next.lap : previous.lap;
			lapProgress = unwrapped % 1;
		}
	}
	return {
		...previous,
		x: previous.x + (next.x - previous.x) * fraction,
		y: previous.y + (next.y - previous.y) * fraction,
		lap,
		lapProgress
	};
}

type TrackCandidate = {
	points: ReplaySample[];
	score: number;
};

const percentile = (values: number[], fraction: number) => {
	if (!values.length) return 0;
	const ordered = [...values].sort((a, b) => a - b);
	return ordered[Math.floor((ordered.length - 1) * fraction)];
};

/** Select a complete, geometrically stable lap and turn it into a closed circuit path. */
export function buildTrackPath(drivers: ReplayDriver[]): TrackPath | null {
	const candidates: TrackCandidate[] = [];
	for (const driver of drivers) {
		const laps = new Map<number, ReplaySample[]>();
		for (const sample of driver.samples) {
			if (sample.lap == null || sample.lapProgress == null) continue;
			const group = laps.get(sample.lap) ?? [];
			group.push(sample);
			laps.set(sample.lap, group);
		}
		for (const samples of laps.values()) {
			samples.sort((a, b) => Number(a.lapProgress) - Number(b.lapProgress));
			if (
				samples.length < 20 ||
				Number(samples[0].lapProgress) > 0.08 ||
				Number(samples.at(-1)?.lapProgress) < 0.92
			)
				continue;
			const steps = samples
				.slice(1)
				.map((point, index) => Math.hypot(point.x - samples[index].x, point.y - samples[index].y))
				.filter((distance) => distance > POSITION_EPSILON);
			const typical = percentile(steps, 0.5);
			const extreme = percentile(steps, 0.99);
			const pathLength = steps.reduce((total, distance) => total + distance, 0);
			const closure = Math.hypot(
				samples.at(-1)!.x - samples[0].x,
				samples.at(-1)!.y - samples[0].y
			);
			const coverage = Number(samples.at(-1)?.lapProgress) - Number(samples[0].lapProgress);
			const score =
				extreme / Math.max(typical, 1) +
				(closure / Math.max(pathLength, 1)) * 10 +
				Math.abs(1 - coverage) * 20;
			candidates.push({ points: samples, score });
		}
	}

	let source = candidates.sort((a, b) => a.score - b.score)[0]?.points;
	if (!source)
		source = [...drivers].sort((a, b) => b.samples.length - a.samples.length)[0]?.samples;
	if (!source?.length) return null;

	const points: TrackPoint[] = [];
	for (const sample of source) {
		const previous = points.at(-1);
		if (!previous || Math.hypot(sample.x - previous.x, sample.y - previous.y) > POSITION_EPSILON)
			points.push({ x: sample.x, y: sample.y });
	}
	if (points.length < 2) return null;
	points.push({ ...points[0] });

	const cumulative = [0];
	for (let index = 1; index < points.length; index += 1) {
		cumulative.push(
			cumulative[index - 1] +
				Math.hypot(points[index].x - points[index - 1].x, points[index].y - points[index - 1].y)
		);
	}
	const length = cumulative.at(-1) ?? 0;
	return length > 0 ? { points, cumulative, length } : null;
}

/** Map monotonic lap progress onto the canonical circuit without using noisy live X/Y. */
export function positionAtTrackProgress(path: TrackPath, progress: number): TrackPoint {
	const bounded = Math.max(0, Math.min(1, Number.isFinite(progress) ? progress : 0));
	const target = bounded * path.length;
	let lo = 1;
	let hi = path.cumulative.length - 1;
	while (lo < hi) {
		const mid = (lo + hi) >> 1;
		if (path.cumulative[mid] < target) lo = mid + 1;
		else hi = mid;
	}
	const previousDistance = path.cumulative[lo - 1];
	const nextDistance = path.cumulative[lo];
	const fraction = (target - previousDistance) / (nextDistance - previousDistance || 1);
	return {
		x: path.points[lo - 1].x + (path.points[lo].x - path.points[lo - 1].x) * fraction,
		y: path.points[lo - 1].y + (path.points[lo].y - path.points[lo - 1].y) * fraction
	};
}

/** Build a compact, parallel pit lane around the start/finish straight. */
export function buildPitLanePath(track: TrackPath): PitLanePath | null {
	if (track.points.length < 3 || track.length <= 0) return null;
	const minX = Math.min(...track.points.map((point) => point.x));
	const maxX = Math.max(...track.points.map((point) => point.x));
	const minY = Math.min(...track.points.map((point) => point.y));
	const maxY = Math.max(...track.points.map((point) => point.y));
	const center = {
		x: track.points.reduce((sum, point) => sum + point.x, 0) / track.points.length,
		y: track.points.reduce((sum, point) => sum + point.y, 0) / track.points.length
	};
	const offset = Math.hypot(maxX - minX, maxY - minY) * 0.025;
	const startProgress = 0.91;
	const progressSpan = 0.18;
	const pointCount = 33;
	const line = positionAtTrackProgress(track, 0);
	const beforeLine = positionAtTrackProgress(track, 0.995);
	const afterLine = positionAtTrackProgress(track, 0.005);
	const tangent = { x: afterLine.x - beforeLine.x, y: afterLine.y - beforeLine.y };
	const tangentLength = Math.hypot(tangent.x, tangent.y) || 1;
	const normal = { x: -tangent.y / tangentLength, y: tangent.x / tangentLength };
	const side = normal.x * (center.x - line.x) + normal.y * (center.y - line.y) >= 0 ? 1 : -1;
	const points = Array.from({ length: pointCount }, (_, index) => {
		const fraction = index / (pointCount - 1);
		const progress = (startProgress + progressSpan * fraction) % 1;
		const base = positionAtTrackProgress(track, progress);
		const lateralOffset = Math.sin(Math.PI * fraction) * offset * side;
		return {
			x: base.x + normal.x * lateralOffset,
			y: base.y + normal.y * lateralOffset
		};
	});
	const cumulative = [0];
	for (let index = 1; index < points.length; index += 1) {
		cumulative.push(
			cumulative[index - 1] +
				Math.hypot(points[index].x - points[index - 1].x, points[index].y - points[index - 1].y)
		);
	}
	const length = cumulative.at(-1) ?? 0;
	return length > 0
		? {
				points,
				cumulative,
				length,
				box: positionAtTrackProgress({ points, cumulative, length }, 0.5)
			}
		: null;
}

/** Return progress through the synthetic pit lane, holding at the box around the event time. */
export function pitLaneProgressAt(driver: ReplayDriver, time: number): number | null {
	const window = driver.pitWindows.find(({ start, end }) => time >= start && time <= end);
	if (!window) return null;
	const holdStart = window.stop - PIT_STOP_HOLD_S / 2;
	const holdEnd = window.stop + PIT_STOP_HOLD_S / 2;
	if (time < holdStart)
		return 0.5 * Math.max(0, Math.min(1, (time - window.start) / (holdStart - window.start || 1)));
	if (time <= holdEnd) return 0.5;
	return 0.5 + 0.5 * Math.max(0, Math.min(1, (time - holdEnd) / (window.end - holdEnd || 1)));
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
	radio: RadioRow[],
	laps: LapRow[] = []
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
	const previousLapByDriver = new Map<string, LapRow>();
	for (const row of [...laps].sort(
		(a, b) =>
			a.driver_code.localeCompare(b.driver_code) ||
			a.lap_number - b.lap_number ||
			a.lap_start_t_s - b.lap_start_t_s
	)) {
		const previous = previousLapByDriver.get(row.driver_code);
		previousLapByDriver.set(row.driver_code, row);
		if (
			!previous ||
			!Number.isFinite(row.lap_start_t_s) ||
			previous.stint == null ||
			row.stint == null ||
			row.stint <= previous.stint
		)
			continue;
		const stopNumber = Math.max(1, Math.round(row.stint) - 1);
		events.push({
			id: `pit|${row.driver_code}|${row.lap_start_t_s}|${stopNumber}`,
			time: row.lap_start_t_s,
			type: 'pit',
			subtype: 'pit',
			label: `${row.driver_code} pit stop`,
			meta: [
				`Lap ${previous.lap_number}`,
				`Stop ${stopNumber}`,
				row.compound ? `Onto ${row.compound.toLowerCase()} tyres` : null
			]
				.filter(Boolean)
				.join(' · '),
			participants: [row.driver_code],
			raw: row
		});
	}
	return events.sort((a, b) => a.time - b.time || a.id.localeCompare(b.id));
}

export function filterEvents(events: ReplayEvent[], selectedCode: string, filter = 'all') {
	return events.filter((event) => {
		if (selectedCode && (event.type === 'control' || !event.participants.includes(selectedCode)))
			return false;
		return filter === 'all' || event.type === filter;
	});
}
